"""Typed, immutable capacity facts. Minting is owned by the Capacity/Model Router."""

from __future__ import annotations

import dataclasses
import re

from control_plane.executive_steward import CapacityState, SourceOwner

_WORKER_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class CapacityOwnerFactError(ValueError):
    """The Capacity owner refused an observation as unsafe or malformed."""


@dataclasses.dataclass(frozen=True, slots=True)
class CapacityOwnerFact:
    worker_id: str
    state: CapacityState
    source: SourceOwner
    generation: int
    _seal: object = dataclasses.field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.worker_id, str)
            or not self.worker_id
            or self.worker_id != self.worker_id.strip()
            or _WORKER_ID_RE.fullmatch(self.worker_id) is None
        ):
            raise CapacityOwnerFactError("capacity worker identity is invalid")
        if self.state is not CapacityState.AVAILABLE:
            raise CapacityOwnerFactError("capacity is not known available")
        if self.source is not SourceOwner.CAPACITY:
            raise CapacityOwnerFactError("capacity source owner is invalid")
        if type(self.generation) is not int or self.generation < 1:
            raise CapacityOwnerFactError("capacity generation is invalid")
        from control_plane.model_router import verify_capacity_owner_fact

        verify_capacity_owner_fact(self)


def export_capacity_fact(**_kwargs):
    raise CapacityOwnerFactError(
        "capacity_fact must be minted by the Capacity owner "
        "(control_plane.model_router.export_capacity_owner_fact)"
    )


__all__ = [
    "CapacityOwnerFact",
    "CapacityOwnerFactError",
    "export_capacity_fact",
]
