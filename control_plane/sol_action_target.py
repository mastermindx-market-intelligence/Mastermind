"""Storeless Stage-A resolution for one action-authoritative Sol target.

The resolver composes two existing sources without persisting either one:

* the exact root-job/CEO-seat alias from :class:`SessionTargetRegistry`; and
* a complete current snapshot of concrete :class:`RuntimeBinding` values.

It deliberately accepts no Slack principal, provider family, model claim,
health, timestamp, title, recency, or caller-supplied alias.  Those facts may
help an operator investigate a missing target, but they cannot elect the Sol
allowed to act on an unresolved semantic turn.

This module owns neither target transfer nor RuntimeBinding persistence.  A
missing exact target remains unavailable; it never promotes a sister Sol.
"""
from __future__ import annotations

import dataclasses
import enum
import hashlib
from collections.abc import Iterable, Mapping

from control_plane.session_targets import (
    RuntimeBinding,
    SessionTarget,
    SessionTargetRegistry,
)
from control_plane.wake_events import JOB_ID_RE, canonical_json_bytes


SCHEMA = "mastermind.sol_action_target.v1"
_TARGET_SEAT = "ceo"


class ActionTargetState(str, enum.Enum):
    RESOLVED = "RESOLVED"
    UNAVAILABLE = "UNAVAILABLE"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"


class ActionTargetReason(str, enum.Enum):
    EXACT_RUNTIME_BINDING = "EXACT_RUNTIME_BINDING"
    ACTOR_OBSERVER_ONLY = "ACTOR_OBSERVER_ONLY"
    ROOT_JOB_ID_MALFORMED = "ROOT_JOB_ID_MALFORMED"
    ROOT_TARGET_MISSING = "ROOT_TARGET_MISSING"
    ROOT_TARGET_CONFLICT = "ROOT_TARGET_CONFLICT"
    BINDING_EVIDENCE_UNKNOWN = "BINDING_EVIDENCE_UNKNOWN"
    TARGET_RUNTIME_UNAVAILABLE = "TARGET_RUNTIME_UNAVAILABLE"
    RUNTIME_BINDING_CONFLICT = "RUNTIME_BINDING_CONFLICT"
    RUNTIME_BINDING_SURFACE_UNKNOWN = "RUNTIME_BINDING_SURFACE_UNKNOWN"
    RUNTIME_BINDING_SURFACE_CONFLICT = "RUNTIME_BINDING_SURFACE_CONFLICT"


class BindingEvidenceState(str, enum.Enum):
    CURRENT = "CURRENT"
    UNKNOWN = "UNKNOWN"


@dataclasses.dataclass(frozen=True)
class RuntimeBindingSnapshot:
    """A read-composed binding snapshot; never a binding registry or writer."""

    state: BindingEvidenceState
    bindings: tuple[RuntimeBinding, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.state, BindingEvidenceState):
            raise TypeError("state must be a BindingEvidenceState")
        if not isinstance(self.bindings, tuple) or not all(
            isinstance(binding, RuntimeBinding) for binding in self.bindings
        ):
            raise TypeError("bindings must be a tuple of RuntimeBinding values")
        if self.state is BindingEvidenceState.UNKNOWN and self.bindings:
            raise ValueError("unknown binding evidence cannot carry partial bindings")

    @classmethod
    def current(
        cls, bindings: Iterable[RuntimeBinding]
    ) -> "RuntimeBindingSnapshot":
        return cls(BindingEvidenceState.CURRENT, tuple(bindings))

    @classmethod
    def unknown(cls) -> "RuntimeBindingSnapshot":
        return cls(BindingEvidenceState.UNKNOWN, ())

    @property
    def evidence_digest(self) -> str:
        rows = sorted(
            (_binding_identity(binding) for binding in self.bindings),
            key=lambda row: (
                row["session_alias"],
                row["binding_id"],
                row["binding_generation"],
                row["reasoning_surface"] or "",
            ),
        )
        return hashlib.sha256(
            canonical_json_bytes(
                {
                    "schema": SCHEMA,
                    "source": "runtime_binding_snapshot",
                    "state": self.state.value,
                    "bindings": rows,
                }
            )
        ).hexdigest()


@dataclasses.dataclass(frozen=True)
class SolActionTargetResolution:
    schema: str
    state: ActionTargetState
    reason: ActionTargetReason
    root_job_id: str
    target_seat: str
    session_alias: str | None
    binding_id: str | None
    binding_generation: int | None
    reasoning_surface: str | None
    action_authoritative: bool
    observer_only: bool
    evidence_digest: str


class SolActionAuthorityError(RuntimeError):
    """The current actor is not the exact action-authoritative Sol target."""

    def __init__(self, resolution: SolActionTargetResolution) -> None:
        super().__init__(
            "Sol action authority refused: "
            f"{resolution.state.value}/{resolution.reason.value}"
        )
        self.resolution = resolution


def resolve_sol_action_target(
    *,
    root_job_id: str,
    registry: SessionTargetRegistry,
    binding_snapshot: RuntimeBindingSnapshot,
    actor_binding: RuntimeBinding | None,
) -> SolActionTargetResolution:
    """Resolve the exact CEO target and determine whether ``actor_binding`` may act.

    Root identity is mandatory and exact.  The registry's root binding wins;
    seat/workstream defaults are never consulted.  A complete binding snapshot
    with no exact target produces ``UNAVAILABLE``.  Missing source evidence,
    multiple exact bindings, or an identity/surface contradiction fails closed.
    """

    if not isinstance(registry, SessionTargetRegistry):
        raise TypeError("registry must be a SessionTargetRegistry")
    if not isinstance(binding_snapshot, RuntimeBindingSnapshot):
        raise TypeError("binding_snapshot must be a RuntimeBindingSnapshot")
    if actor_binding is not None and not isinstance(actor_binding, RuntimeBinding):
        raise TypeError("actor_binding must be RuntimeBinding or None")

    root = root_job_id if isinstance(root_job_id, str) else ""
    if JOB_ID_RE.fullmatch(root) is None:
        return _resolution(
            state=ActionTargetState.UNKNOWN,
            reason=ActionTargetReason.ROOT_JOB_ID_MALFORMED,
            root_job_id=root,
            registry=registry,
            binding_snapshot=binding_snapshot,
            actor_binding=actor_binding,
        )

    seat_map = registry.root_job_bindings.get(root)
    if not isinstance(seat_map, Mapping):
        return _resolution(
            state=ActionTargetState.UNKNOWN,
            reason=ActionTargetReason.ROOT_TARGET_MISSING,
            root_job_id=root,
            registry=registry,
            binding_snapshot=binding_snapshot,
            actor_binding=actor_binding,
        )
    alias = seat_map.get(_TARGET_SEAT)
    if not isinstance(alias, str) or not alias:
        return _resolution(
            state=ActionTargetState.UNKNOWN,
            reason=ActionTargetReason.ROOT_TARGET_MISSING,
            root_job_id=root,
            registry=registry,
            binding_snapshot=binding_snapshot,
            actor_binding=actor_binding,
        )

    target = registry.targets.get(alias)
    if not isinstance(target, SessionTarget) or target.target_seat != _TARGET_SEAT:
        return _resolution(
            state=ActionTargetState.CONFLICT,
            reason=ActionTargetReason.ROOT_TARGET_CONFLICT,
            root_job_id=root,
            registry=registry,
            binding_snapshot=binding_snapshot,
            actor_binding=actor_binding,
            session_alias=alias,
        )

    if binding_snapshot.state is BindingEvidenceState.UNKNOWN:
        return _resolution(
            state=ActionTargetState.UNKNOWN,
            reason=ActionTargetReason.BINDING_EVIDENCE_UNKNOWN,
            root_job_id=root,
            registry=registry,
            binding_snapshot=binding_snapshot,
            actor_binding=actor_binding,
            session_alias=alias,
        )

    candidates = tuple(
        binding
        for binding in binding_snapshot.bindings
        if binding.session_alias == alias
    )
    if not candidates:
        return _resolution(
            state=ActionTargetState.UNAVAILABLE,
            reason=ActionTargetReason.TARGET_RUNTIME_UNAVAILABLE,
            root_job_id=root,
            registry=registry,
            binding_snapshot=binding_snapshot,
            actor_binding=actor_binding,
            session_alias=alias,
        )
    if len(candidates) != 1:
        return _resolution(
            state=ActionTargetState.CONFLICT,
            reason=ActionTargetReason.RUNTIME_BINDING_CONFLICT,
            root_job_id=root,
            registry=registry,
            binding_snapshot=binding_snapshot,
            actor_binding=actor_binding,
            session_alias=alias,
        )

    binding = candidates[0]
    if binding.reasoning_surface is None:
        return _resolution(
            state=ActionTargetState.UNKNOWN,
            reason=ActionTargetReason.RUNTIME_BINDING_SURFACE_UNKNOWN,
            root_job_id=root,
            registry=registry,
            binding_snapshot=binding_snapshot,
            actor_binding=actor_binding,
            session_alias=alias,
        )
    if binding.reasoning_surface != target.reasoning_surface:
        return _resolution(
            state=ActionTargetState.CONFLICT,
            reason=ActionTargetReason.RUNTIME_BINDING_SURFACE_CONFLICT,
            root_job_id=root,
            registry=registry,
            binding_snapshot=binding_snapshot,
            actor_binding=actor_binding,
            session_alias=alias,
        )

    authoritative = _same_binding(actor_binding, binding)
    return _resolution(
        state=ActionTargetState.RESOLVED,
        reason=(
            ActionTargetReason.EXACT_RUNTIME_BINDING
            if authoritative
            else ActionTargetReason.ACTOR_OBSERVER_ONLY
        ),
        root_job_id=root,
        registry=registry,
        binding_snapshot=binding_snapshot,
        actor_binding=actor_binding,
        session_alias=alias,
        binding=binding,
        action_authoritative=authoritative,
    )


def require_sol_action_authority(
    resolution: SolActionTargetResolution,
) -> SolActionTargetResolution:
    """Return an exact authoritative resolution or raise a typed refusal."""

    if not isinstance(resolution, SolActionTargetResolution):
        raise TypeError("resolution must be a SolActionTargetResolution")
    if (
        resolution.state is not ActionTargetState.RESOLVED
        or not resolution.action_authoritative
    ):
        raise SolActionAuthorityError(resolution)
    return resolution


def _same_binding(
    actor: RuntimeBinding | None, target: RuntimeBinding
) -> bool:
    return actor is not None and _binding_identity(actor) == _binding_identity(target)


def _binding_identity(binding: RuntimeBinding) -> dict[str, object]:
    return {
        "session_alias": binding.session_alias,
        "binding_id": binding.binding_id,
        "binding_generation": binding.binding_generation,
        "reasoning_surface": binding.reasoning_surface,
    }


def _resolution(
    *,
    state: ActionTargetState,
    reason: ActionTargetReason,
    root_job_id: str,
    registry: SessionTargetRegistry,
    binding_snapshot: RuntimeBindingSnapshot,
    actor_binding: RuntimeBinding | None,
    session_alias: str | None = None,
    binding: RuntimeBinding | None = None,
    action_authoritative: bool = False,
) -> SolActionTargetResolution:
    binding_id = binding.binding_id if binding is not None else None
    binding_generation = (
        binding.binding_generation if binding is not None else None
    )
    reasoning_surface = (
        binding.reasoning_surface if binding is not None else None
    )
    digest = hashlib.sha256(
        canonical_json_bytes(
            {
                "schema": SCHEMA,
                "state": state.value,
                "reason": reason.value,
                "root_job_id": root_job_id,
                "target_seat": _TARGET_SEAT,
                "session_alias": session_alias,
                "binding_id": binding_id,
                "binding_generation": binding_generation,
                "reasoning_surface": reasoning_surface,
                "actor_binding": (
                    _binding_identity(actor_binding)
                    if actor_binding is not None
                    else None
                ),
                "action_authoritative": action_authoritative,
                "policy_digest": registry.policy_digest(),
                "binding_snapshot_digest": binding_snapshot.evidence_digest,
            }
        )
    ).hexdigest()
    return SolActionTargetResolution(
        schema=SCHEMA,
        state=state,
        reason=reason,
        root_job_id=root_job_id,
        target_seat=_TARGET_SEAT,
        session_alias=session_alias,
        binding_id=binding_id,
        binding_generation=binding_generation,
        reasoning_surface=reasoning_surface,
        action_authoritative=action_authoritative,
        observer_only=actor_binding is not None and not action_authoritative,
        evidence_digest=digest,
    )


__all__ = [
    "ActionTargetReason",
    "ActionTargetState",
    "BindingEvidenceState",
    "RuntimeBindingSnapshot",
    "SCHEMA",
    "SolActionAuthorityError",
    "SolActionTargetResolution",
    "require_sol_action_authority",
    "resolve_sol_action_target",
]
