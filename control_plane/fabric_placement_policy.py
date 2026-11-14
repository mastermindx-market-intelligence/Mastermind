"""Rev5 D6 parent-as-placement policy (pure decision core).

Change order: Fable Wave 3 R5 §3D; master plan §3 "Placement unit and
locality" (l.114–133) and §5 "Reservation and identity" (l.243–271,
esp. l.269–271).

This module owns NO store, no scheduler, no service and no network: every
function is a pure predicate/render over an immutable
:class:`PlacementIntent` record and plain numbers a caller read from its
current Runtime transaction — the same contract as
:mod:`control_plane.child_request_admission` (WO-13).  The claim path in
``control_plane.executive_runtime`` (the existing sole placement
authority; WO-14) calls this module and nothing else for D6 decisions.

Law embedded here:

* **Parent and children are separate placement requests.**  A parent
  actor on host X requesting N children reserves ZERO local child slots
  for them: :func:`fabric_per_child` children are independently placed
  across qualified hosts and the descendant limit is an ADMISSION CAP
  checked at each child claim (:func:`descendant_admission`), never a
  pre-reserved slot (:func:`fanout_envelope_slots` returns 0).
* **Parent-host is a SOFT preference only.**  Warm dependencies, repo
  cache and lower transfer cost reorder candidates (:func:`soft_preference_key`
  / :func:`apply_locality`); they never exclude a host.  HARD affinity
  exists only when the request declares a real local dependency
  (``required_local_dependency_refs``): :func:`classify_locality` is
  ``HARD_AFFINITY`` exactly then, the candidate set narrows to hosts
  whose capability snapshot declares the refs, and work that cannot fit
  QUEUES (``NO_ELIGIBLE_CANDIDATE`` / ``HOST_CAPACITY_EXHAUSTED`` /
  headroom) — it never evades a cap.
* **Conservative turn reservation.**  No verified runtime yield hook
  exists yet (§5 l.269–271), so a parent holds its host slot + root
  concurrency for the whole managed native turn, its resident memory and
  active tools stay counted, and there is NO mid-turn release:
  :class:`TurnReservation` cannot be constructed with
  ``mid_turn_release`` truthy.
* **Explicit child headroom.**  Parents waiting inside opaque turns must
  not consume every slot: :class:`ChildHeadroomPolicy` reserves
  ``max(1, slots // 4)`` child slots per host (environment-tunable via
  ``MMOS_FABRIC_CHILD_HEADROOM``) and a parent-role placement may never
  take the last headroom slot (:attr:`PARENT_HEADROOM_EXHAUSTED`).
* **Never double-reserve envelope + children.**  The default
  ``fabric_per_child`` pre-reserves nothing.  A declared
  ``bounded_native_fanout`` parent reserves its enforced fan-out envelope
  AT THE PARENT'S HOST at claim (:func:`fanout_envelope_slots`,
  :func:`inflate_host_slot_demand`); children under that policy skip the
  per-claim descendant count because the envelope already reserved their
  capacity — the same bound is never applied twice.
"""

from __future__ import annotations

import enum
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

__all__ = [
    "PLACEMENT_INTENT_SCHEMA",
    "HEADROOM_ENV",
    "PARENT_HEADROOM_EXHAUSTED",
    "DESCENDANT_CONCURRENCY_EXHAUSTED",
    "NO_ELIGIBLE_CANDIDATE",
    "FABRIC_HEADROOM_RATE",
    "MAX_TOKEN_LENGTH",
    "MAX_FANOUT_LIMIT",
    "ActorRole",
    "WorkspaceMode",
    "LocalityClass",
    "DescendantPolicy",
    "ResourceProfile",
    "PlacementIntent",
    "TurnReservation",
    "HeadroomVerdict",
    "ChildHeadroomPolicy",
    "intent_digest",
    "classify_locality",
    "soft_preference_key",
    "apply_locality",
    "filter_hard_affinity_hosts",
    "descendant_policy",
    "descendant_admission",
    "fabric_per_child",
    "fanout_envelope_slots",
    "inflate_host_slot_demand",
    "reserve_turn_for_intent",
]

#: Schema of the D6 wire record :meth:`PlacementIntent.to_dict` emits and
#: :meth:`PlacementIntent.from_dict` accepts.
PLACEMENT_INTENT_SCHEMA = "mastermind.fabric_placement_intent.v1"

#: Environment override of the per-host reserved child-slot headroom.
HEADROOM_ENV = "MMOS_FABRIC_CHILD_HEADROOM"

#: Default reserved child slots per host: max(1, slots // 4) — 1 of every
#: four host slots stays reserved for children (FABRIC_HEADROOM_RATE).
FABRIC_HEADROOM_RATE = 4

#: Blocked reasons returned to the claim path (never a cap evasion).
PARENT_HEADROOM_EXHAUSTED = "PARENT_HEADROOM_EXHAUSTED"
DESCENDANT_CONCURRENCY_EXHAUSTED = "DESCENDANT_CONCURRENCY_EXHAUSTED"
NO_ELIGIBLE_CANDIDATE = "NO_ELIGIBLE_CANDIDATE"

MAX_TOKEN_LENGTH = 256
MAX_FANOUT_LIMIT = 10_000
_SPEC_DIGEST_RE = re.compile(r"[0-9a-f]{64}")


class _ValueEnum(str, enum.Enum):
    """String enum whose value is the public wire value (existing idiom)."""


class ActorRole(_ValueEnum):
    """Every placement request is for ONE actor: a parent or a child."""

    PARENT = "parent"
    CHILD = "child"


class WorkspaceMode(_ValueEnum):
    """The supported workspace intent (§3 l.127)."""

    READ_ONLY_SNAPSHOT = "read_only_snapshot"
    SINGLE_WRITER = "single_writer"
    ISOLATED_PATCH = "isolated_patch"


class LocalityClass(_ValueEnum):
    """SOFT preference reorders candidates only; HARD affinity filters."""

    SOFT_PREFERENCE = "soft_preference"
    HARD_AFFINITY = "hard_affinity"


class DescendantPolicy(_ValueEnum):
    """How a root's descendants acquire capacity.

    ``fabric_per_child`` (default): children get their own placements;
    the descendant limit is an admission cap checked at each child claim.
    ``bounded_native_fanout``: children run natively under the parent's
    host executor; the envelope is reserved at the parent's host at the
    parent's claim and the per-claim cap is not applied again.
    """

    FABRIC_PER_CHILD = "fabric_per_child"
    BOUNDED_NATIVE_FANOUT = "bounded_native_fanout"


# ---------------------------------------------------------------------------
# token law (mirrors executive_placement_selection's secret-safe validator)
# ---------------------------------------------------------------------------

def _require_token(name: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_TOKEN_LENGTH
        or any(ch.isspace() for ch in value)
        or "@" in value
        or "/" in value
        or "\\" in value
        or any(not ch.isprintable() for ch in value)
    ):
        raise ValueError(
            f"{name} must be a non-empty token of at most {MAX_TOKEN_LENGTH} "
            "characters with no whitespace, '@', '/', backslash, or control "
            "characters"
        )
    return value


def _optional_token(name: str, value: object) -> str:
    if value is None or value == "":
        return ""
    return _require_token(name, value)


def _ref_list(name: str, value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ValueError(f"{name} must be a list of tokens")
    tokens = [_require_token(f"{name} item", item) for item in value]
    if len(set(tokens)) != len(tokens):
        raise ValueError(f"{name} must be duplicate-free")
    return tuple(tokens)


def _optional_digest(name: str, value: object) -> str:
    if value is None or value == "":
        return ""
    if not isinstance(value, str) or not _SPEC_DIGEST_RE.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase 64-hex digest when set")
    return value


def _optional_nonneg_int(name: str, value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer or None")
    return value


# ---------------------------------------------------------------------------
# the PlacementIntent.v1 record (§3 l.119–125)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResourceProfile:
    """The counted footprint the placement reserves for the whole turn."""

    resident_memory_bytes: int = 0
    active_tools: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.resident_memory_bytes) is not int or self.resident_memory_bytes < 0:
            raise ValueError("resident_memory_bytes must be a nonnegative integer")
        object.__setattr__(
            self, "active_tools", _ref_list("active_tools", self.active_tools)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "resident_memory_bytes": int(self.resident_memory_bytes),
            "active_tools": list(self.active_tools),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any] | None) -> "ResourceProfile":
        if raw is None:
            return cls()
        if not isinstance(raw, Mapping):
            raise ValueError("resource_profile must be a mapping")
        unknown = set(raw) - {"resident_memory_bytes", "active_tools"}
        if unknown:
            raise ValueError(f"resource_profile has unknown keys {sorted(unknown)}")
        return cls(
            resident_memory_bytes=raw.get("resident_memory_bytes") or 0,
            active_tools=tuple(raw.get("active_tools") or ()),
        )


_INTENT_REQUIRED_KEYS = frozenset({
    "schema", "root_run_id", "immediate_parent_run_id", "logical_child_id",
    "operation_id", "actor_role",
})
_INTENT_KEYS = _INTENT_REQUIRED_KEYS | {
    "runtime_kind", "required_capabilities", "task_class", "root_budget_ref",
    "descendant_parallelism_limit", "descendant_policy", "preferred_host",
    "required_local_dependency_refs", "workspace_mode", "workspace_ref",
    "base_revision", "source_scope_digest", "resource_profile", "priority",
    "deadline_ms", "expiry_ms",
}


@dataclass(frozen=True)
class PlacementIntent:
    """One bounded, validated D6 placement request (§3 l.119–125).

    Every field is a bounded reference — none of them is a credential.
    ``immediate_parent_run_id`` / ``root_run_id`` carry the §5 authority
    lineage; ``source_scope_digest`` is a 64-hex digest of the demanded
    source scope, never a path.
    """

    root_run_id: str
    immediate_parent_run_id: str
    logical_child_id: str
    operation_id: str
    actor_role: ActorRole
    runtime_kind: str = "native_process"
    required_capabilities: tuple[str, ...] = ()
    task_class: str = ""
    root_budget_ref: str = ""
    descendant_parallelism_limit: int | None = None
    descendant_policy: DescendantPolicy = DescendantPolicy.FABRIC_PER_CHILD
    preferred_host: str = ""
    required_local_dependency_refs: tuple[str, ...] = ()
    workspace_mode: WorkspaceMode = WorkspaceMode.READ_ONLY_SNAPSHOT
    workspace_ref: str = ""
    base_revision: str = ""
    source_scope_digest: str = ""
    resource_profile: ResourceProfile = field(default_factory=ResourceProfile)
    priority: int = 0
    deadline_ms: int | None = None
    expiry_ms: int | None = None

    def __post_init__(self) -> None:
        _require_token("root_run_id", self.root_run_id)
        _require_token("immediate_parent_run_id", self.immediate_parent_run_id)
        _require_token("logical_child_id", self.logical_child_id)
        _require_token("operation_id", self.operation_id)
        if not isinstance(self.actor_role, ActorRole):
            raise TypeError("actor_role must be an ActorRole")
        _optional_token("runtime_kind", self.runtime_kind)
        object.__setattr__(
            self,
            "required_capabilities",
            _ref_list("required_capabilities", self.required_capabilities),
        )
        _optional_token("task_class", self.task_class)
        _optional_token("root_budget_ref", self.root_budget_ref)
        if self.descendant_parallelism_limit is not None and (
            type(self.descendant_parallelism_limit) is not int
            or not 1 <= self.descendant_parallelism_limit <= MAX_FANOUT_LIMIT
        ):
            raise ValueError(
                "descendant_parallelism_limit must be an integer in "
                f"[1, {MAX_FANOUT_LIMIT}] or None"
            )
        if not isinstance(self.descendant_policy, DescendantPolicy):
            raise TypeError("descendant_policy must be a DescendantPolicy")
        if (
            self.descendant_policy is DescendantPolicy.BOUNDED_NATIVE_FANOUT
            and self.descendant_parallelism_limit is None
        ):
            raise ValueError(
                "bounded_native_fanout declares an enforced fan-out envelope: "
                "descendant_parallelism_limit is required"
            )
        _optional_token("preferred_host", self.preferred_host)
        object.__setattr__(
            self,
            "required_local_dependency_refs",
            _ref_list("required_local_dependency_refs",
                      self.required_local_dependency_refs),
        )
        if not isinstance(self.workspace_mode, WorkspaceMode):
            raise TypeError("workspace_mode must be a WorkspaceMode")
        if self.workspace_mode is not WorkspaceMode.READ_ONLY_SNAPSHOT and not self.workspace_ref:
            raise ValueError(
                f"workspace_ref is required for workspace_mode={self.workspace_mode.value}"
            )
        _optional_token("workspace_ref", self.workspace_ref)
        _optional_token("base_revision", self.base_revision)
        object.__setattr__(self, "source_scope_digest",
                           _optional_digest("source_scope_digest",
                                            self.source_scope_digest))
        if not isinstance(self.resource_profile, ResourceProfile):
            raise TypeError("resource_profile must be a ResourceProfile")
        if type(self.priority) is not int or not -1000 <= self.priority <= 1000:
            raise ValueError("priority must be an integer in [-1000, 1000]")
        object.__setattr__(self, "deadline_ms",
                           _optional_nonneg_int("deadline_ms", self.deadline_ms))
        object.__setattr__(self, "expiry_ms",
                           _optional_nonneg_int("expiry_ms", self.expiry_ms))

    # -- wire ---------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return dict(
            schema=PLACEMENT_INTENT_SCHEMA,
            root_run_id=self.root_run_id,
            immediate_parent_run_id=self.immediate_parent_run_id,
            logical_child_id=self.logical_child_id,
            operation_id=self.operation_id,
            actor_role=self.actor_role.value,
            runtime_kind=self.runtime_kind,
            required_capabilities=list(self.required_capabilities),
            task_class=self.task_class,
            root_budget_ref=self.root_budget_ref,
            descendant_parallelism_limit=self.descendant_parallelism_limit,
            descendant_policy=self.descendant_policy.value,
            preferred_host=self.preferred_host,
            required_local_dependency_refs=list(self.required_local_dependency_refs),
            workspace_mode=self.workspace_mode.value,
            workspace_ref=self.workspace_ref,
            base_revision=self.base_revision,
            source_scope_digest=self.source_scope_digest,
            resource_profile=self.resource_profile.to_dict(),
            priority=int(self.priority),
            deadline_ms=self.deadline_ms,
            expiry_ms=self.expiry_ms,
        )

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any] | None) -> "PlacementIntent":
        if not isinstance(raw, Mapping):
            raise ValueError("fabric placement intent must be a mapping")
        unknown = set(raw) - _INTENT_KEYS
        if unknown:
            raise ValueError(f"fabric placement intent has unknown keys {sorted(unknown)}")
        missing = {key for key in _INTENT_REQUIRED_KEYS - {"schema"} if raw.get(key) in (None, "")}
        if missing:
            raise ValueError(f"fabric placement intent is missing {sorted(missing)}")
        if raw.get("schema", PLACEMENT_INTENT_SCHEMA) != PLACEMENT_INTENT_SCHEMA:
            raise ValueError("fabric placement intent schema is not v1")
        actor_role = raw["actor_role"]
        if not isinstance(actor_role, str):
            raise ValueError("actor_role must be a token")
        try:
            role = ActorRole(actor_role)
        except ValueError as exc:
            raise ValueError(f"actor_role {actor_role!r} is not a parent or child") from exc
        capabilities = raw.get("required_capabilities") or []
        if isinstance(capabilities, str) or not isinstance(capabilities, (list, tuple)):
            raise ValueError("required_capabilities must be a list of tokens")
        workspace_mode = raw.get("workspace_mode")
        if workspace_mode is not None:
            if not isinstance(workspace_mode, str):
                raise ValueError("workspace_mode must be a token")
            try:
                workspace_mode = WorkspaceMode(workspace_mode)
            except ValueError as exc:
                raise ValueError(f"workspace_mode {workspace_mode!r} is not supported") from exc
        descendant_policy = raw.get("descendant_policy")
        if descendant_policy is not None:
            if not isinstance(descendant_policy, str):
                raise ValueError("descendant_policy must be a token")
            try:
                descendant_policy = DescendantPolicy(descendant_policy)
            except ValueError as exc:
                raise ValueError(f"descendant_policy {descendant_policy!r} is not declared") from exc
        try:
            resource_profile = ResourceProfile.from_dict(raw.get("resource_profile"))
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return cls(
            root_run_id=raw["root_run_id"],
            immediate_parent_run_id=raw["immediate_parent_run_id"],
            logical_child_id=raw["logical_child_id"],
            operation_id=raw["operation_id"],
            actor_role=role,
            runtime_kind=raw.get("runtime_kind") or "native_process",
            required_capabilities=tuple(capabilities),
            task_class=raw.get("task_class") or "",
            root_budget_ref=raw.get("root_budget_ref") or "",
            descendant_parallelism_limit=raw.get("descendant_parallelism_limit"),
            descendant_policy=descendant_policy or DescendantPolicy.FABRIC_PER_CHILD,
            preferred_host=raw.get("preferred_host") or "",
            required_local_dependency_refs=tuple(raw.get("required_local_dependency_refs") or ()),
            workspace_mode=workspace_mode or WorkspaceMode.READ_ONLY_SNAPSHOT,
            workspace_ref=raw.get("workspace_ref") or "",
            base_revision=raw.get("base_revision") or "",
            source_scope_digest=raw.get("source_scope_digest") or "",
            resource_profile=resource_profile,
            priority=raw.get("priority") or 0,
            deadline_ms=raw.get("deadline_ms"),
            expiry_ms=raw.get("expiry_ms"),
        )


def intent_digest(intent: PlacementIntent) -> str:
    """The stable digest of the intent record (sha256 of canonical json)."""
    canonical = json.dumps(intent.to_dict(), sort_keys=True,
                           separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# locality: soft preference reorders, hard affinity filters (§3 l.129–133)
# ---------------------------------------------------------------------------

def classify_locality(intent: PlacementIntent) -> LocalityClass:
    """HARD affinity iff the request DECLARES a real local dependency.

    A declared local service / nonportable dependency / exact mutable
    workspace lease travels in ``required_local_dependency_refs``;
    everything else — including a mere ``preferred_host`` — stays a soft
    preference.
    """
    if intent.required_local_dependency_refs:
        return LocalityClass.HARD_AFFINITY
    return LocalityClass.SOFT_PREFERENCE


def soft_preference_key(host_id: str, intent: PlacementIntent) -> int:
    """Stable ranking key: the warm/cheaper preferred host scores first.

    A host the request does not prefer keeps its input order — soft
    locality NEVER excludes a candidate, it reorders candidates by score
    only.
    """
    if intent.preferred_host and host_id == intent.preferred_host:
        return 0
    return 1


def _affinity_declared(
    declare: Callable[[str], bool],
    intent: PlacementIntent,
    host_id: str,
) -> bool:
    return bool(host_id) and declare(host_id)


def filter_hard_affinity_hosts(
    host_ids: Sequence[str],
    intent: PlacementIntent,
    declare: Callable[[str], bool],
) -> tuple[tuple[str, ...], str | None]:
    """Narrow hard-affinity candidates to hosts that DECLARE the dependency.

    ``declare(host_id)`` answers whether the host's capability snapshot
    declares every ``required_local_dependency_refs`` ref.  Returns the
    kept (bounded, input-ordered) host ids, or a blocking
    ``NO_ELIGIBLE_CANDIDATE`` reason when NO host declares the
    dependency — the work then QUEUES; it never evades the cap by
    running where the dependency is missing.
    """
    if classify_locality(intent) is not LocalityClass.HARD_AFFINITY:
        return tuple(host_ids), None
    required = intent.required_local_dependency_refs
    if not required:  # unreachable by construction; belt-and-braces
        return tuple(host_ids), None
    kept = tuple(
        host_id for host_id in host_ids
        if _affinity_declared(declare, intent, host_id)
    )
    if not kept:
        return (), NO_ELIGIBLE_CANDIDATE
    return kept, None


def apply_locality(
    host_ids: Sequence[str],
    intent: PlacementIntent,
    declare: Callable[[str], bool] | None = None,
) -> tuple[tuple[str, ...], str | None]:
    """One call-side entry point for D6 locality over candidate hosts.

    Soft preference: stable reorder, preferred host first, NOTHING
    excluded.  Hard affinity: the declared-only subset, or the blocking
    reason when none declares.
    """
    if intent is None:
        return tuple(host_ids), None
    if classify_locality(intent) is LocalityClass.HARD_AFFINITY:
        return filter_hard_affinity_hosts(
            host_ids, intent, declare or (lambda host_id: False)
        )
    preferred = intent.preferred_host
    if not preferred or preferred not in set(host_ids):
        return tuple(host_ids), None
    ordered = tuple([preferred]) + tuple(h for h in host_ids if h != preferred)
    return ordered, None


# ---------------------------------------------------------------------------
# descendant policy: counted cap vs reserved envelope (§3D; §5 l.269–271)
# ---------------------------------------------------------------------------

def descendant_policy(intent: PlacementIntent) -> DescendantPolicy:
    return intent.descendant_policy


def fabric_per_child(intent: PlacementIntent) -> bool:
    return intent.descendant_policy is DescendantPolicy.FABRIC_PER_CHILD


@dataclass(frozen=True)
class DescendantVerdict:
    ok: bool
    reason: str | None = None
    detail: str = ""


def descendant_admission(
    intent: PlacementIntent,
    sibling_active_attempts: int,
) -> DescendantVerdict:
    """The at-claim admission cap for one MORE child under a root.

    ``sibling_active_attempts`` counts the root's other active attempts
    (the caller counts them from its own transaction).  For the default
    ``fabric_per_child`` the limit is a COUNTED admission cap: the N+1th
    concurrent child is refused with ``DESCENDANT_CONCURRENCY_EXHAUSTED``
    and queues — it never evades the cap.  A ``bounded_native_fanout``
    child is NOT counted here: its capacity was reserved in the parent's
    envelope at the parent's claim, so the same bound is never applied
    twice (never double-reserve envelope + children).
    """
    if intent.descendant_policy is DescendantPolicy.BOUNDED_NATIVE_FANOUT:
        return DescendantVerdict(ok=True)
    limit = intent.descendant_parallelism_limit
    if limit is None or type(limit) is not int:
        return DescendantVerdict(ok=True)
    active = int(sibling_active_attempts)
    if active >= limit:
        return DescendantVerdict(
            ok=False, reason=DESCENDANT_CONCURRENCY_EXHAUSTED,
            detail=f"{active}/{limit} concurrent descendants",
        )
    return DescendantVerdict(ok=True)


def fanout_envelope_slots(intent: PlacementIntent) -> int:
    """Slots the claim itself must reserve for its declared fan-out.

    Only a ``bounded_native_fanout`` PARENT reserves an envelope at its
    host at claim — ``fabric_per_child`` reserves ZERO local slots for
    children no matter how many were requested (a parent requesting 20
    children reserves 0 of them locally; §3 l.135–137).
    """
    if (
        intent.actor_role is ActorRole.PARENT
        and intent.descendant_policy is DescendantPolicy.BOUNDED_NATIVE_FANOUT
    ):
        limit = intent.descendant_parallelism_limit
        return int(limit) if limit else 0
    return 0


def inflate_host_slot_demand(
    request: Mapping[str, Any],
    *,
    host_slot_pool_id: str,
    envelope: int,
) -> dict[str, Any]:
    """Fold the fan-out envelope into the claim's ONE host-slot demand.

    The envelope is reserved at the parent's host BY the parent's own
    placement commitment: the existing ``host_slot_pool`` demand bound to
    the attempt is inflated so the held charge covers 1 + envelope slots
    until settlement.  Pure; returns a modified copy and refuses an
    unknown pool so an envelope can never silently vanish.
    """
    if type(envelope) is not int or envelope < 0:
        raise ValueError("envelope must be a nonnegative integer")
    if envelope == 0:
        return dict(request)
    phases = request.get("phases")
    if not isinstance(phases, list) or not phases:
        raise ValueError("physical request carries no phases")
    folded = False
    copied_phases: list[Any] = []
    for phase in phases:
        if not isinstance(phase, Mapping):
            raise ValueError("physical request phase is not a mapping")
        demands = []
        phase_copy = dict(phase)
        for demand in phase.get("demands") or ():
            item = dict(demand)
            if item.get("capacity_pool_id") == host_slot_pool_id:
                peak = item.get("qualified_incremental_peak")
                if type(peak) is not int or peak <= 0:
                    raise ValueError("host slot demand is not a positive peak")
                item["qualified_incremental_peak"] = peak + envelope
                folded = True
            demands.append(item)
        phase_copy["demands"] = demands
        copied_phases.append(phase_copy)
    if not folded:
        raise ValueError(f"physical request has no demand on {host_slot_pool_id}")
    return dict(request, phases=copied_phases)


# ---------------------------------------------------------------------------
# child headroom: parents never consume the reserved child slots
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HeadroomVerdict:
    ok: bool
    reason: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class ChildHeadroomPolicy:
    """Per-host reserved child slots so waiting parents cannot starve them.

    Default: ``max(1, slots // 4)`` of every host's slots stay reserved
    for children.  ``MMOS_FABRIC_CHILD_HEADROOM`` overrides the absolute
    reserved count host-independently (0 disables the reservation).  A
    CHILD placement may always use the reserved slots; a PARENT
    placement is refused with ``PARENT_HEADROOM_EXHAUSTED`` when taking
    its slot would leave fewer than the headroom free.
    """

    reserved_child_slots_override: int | None = None

    def __post_init__(self) -> None:
        if self.reserved_child_slots_override is not None and (
            type(self.reserved_child_slots_override) is not int
            or self.reserved_child_slots_override < 0
        ):
            raise ValueError("reserved_child_slots_override must be a nonnegative integer or None")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ChildHeadroomPolicy":
        source = os.environ if env is None else env
        raw = source.get(HEADROOM_ENV)
        if raw is None or str(raw).strip() == "":
            return cls()
        try:
            override = int(str(raw).strip())
        except ValueError as exc:
            raise ValueError(
                f"{HEADROOM_ENV} must be an integer, got {raw!r}") from exc
        if override < 0:
            raise ValueError(f"{HEADROOM_ENV} must be a nonnegative integer")
        return cls(reserved_child_slots_override=override)

    def reserved_child_slots(self, host_slots_total: int) -> int:
        if type(host_slots_total) is not int or host_slots_total < 0:
            raise ValueError("host_slots_total must be a nonnegative integer")
        if self.reserved_child_slots_override is not None:
            return min(self.reserved_child_slots_override, host_slots_total)
        return max(1, host_slots_total // FABRIC_HEADROOM_RATE)

    def admit_against_headroom(
        self,
        host_slots_total: int,
        parent_placements: int,
        child_placements: int,
        *,
        is_parent: bool,
    ) -> HeadroomVerdict:
        """May THIS placement take one more slot on the host?

        ``parent_placements`` / ``child_placements`` count the host's
        ACTIVE placements by claim role.  A parent may only take a slot
        that leaves at least :meth:`reserved_child_slots` free for
        children; children are admitted against the host capacity alone
        (checked by the existing placement predicate) and may consume the
        headroom freely.
        """
        total = int(host_slots_total)
        taken = int(parent_placements) + int(child_placements)
        headroom = self.reserved_child_slots(total)
        free_after = total - taken - 1
        if is_parent and free_after < headroom:
            return HeadroomVerdict(
                ok=False, reason=PARENT_HEADROOM_EXHAUSTED,
                detail=(
                    f"{taken}/{total} slots held; the last {headroom} stay "
                    "reserved for children"
                ),
            )
        return HeadroomVerdict(ok=True)


# ---------------------------------------------------------------------------
# conservative turn reservation (§5 l.269–271)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TurnReservation:
    """What a parent's claim holds for the WHOLE managed native turn.

    No verified runtime yield hook exists yet, so the reservation is
    conservative: host slot + root concurrency are held until
    settlement, the resident memory and active tools stay counted, and
    there is NO mid-turn release — the invariant is enforced by
    construction below.
    """

    host_slot: bool = True
    root_concurrency: bool = True
    resident_memory_bytes: int = 0
    active_tools: tuple[str, ...] = ()
    envelope_slots: int = 0

    def __post_init__(self) -> None:
        if not self.host_slot or not self.root_concurrency:
            raise ValueError(
                "a conservative turn reservation holds the host slot and the "
                "root concurrency until settlement: no mid-turn release"
            )
        if type(self.resident_memory_bytes) is not int or self.resident_memory_bytes < 0:
            raise ValueError("resident_memory_bytes must be a nonnegative integer")
        if type(self.envelope_slots) is not int or self.envelope_slots < 0:
            raise ValueError("envelope_slots must be a nonnegative integer")

    def to_dict(self) -> dict[str, Any]:
        return dict(
            held=["host_slot", "root_concurrency"],
            resident_memory_bytes=int(self.resident_memory_bytes),
            active_tools=list(self.active_tools),
            envelope_slots=int(self.envelope_slots),
            mid_turn_release=False,
        )


def reserve_turn_for_intent(intent: PlacementIntent | None) -> TurnReservation:
    """The conservative reservation model for one placement intent."""
    profile = intent.resource_profile if intent is not None else ResourceProfile()
    return TurnReservation(
        resident_memory_bytes=int(profile.resident_memory_bytes),
        active_tools=tuple(profile.active_tools),
        envelope_slots=fanout_envelope_slots(intent) if intent is not None else 0,
    )
