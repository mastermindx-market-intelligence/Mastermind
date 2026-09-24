"""Structured, deterministic defects for the EVAL-R0 evaluation core.

Every rejection in this package is a :class:`ContractDefect` — a machine
sortable ``(path, code, message)`` triple — never a bare string or a Python
built-in exception carrying prose. Defects are always deterministically
ordered so a reviewer sees a stable failure list regardless of dict/set
iteration order upstream.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, order=True)
class ContractDefect:
    """One deterministic, sortable shape/graph/privacy defect.

    Ordered by ``(path, code, message)`` so a list of defects always prints
    in the same order regardless of discovery order.
    """

    path: str
    code: str
    message: str = field(default="")


def _sorted_unique(defects) -> tuple[ContractDefect, ...]:
    seen: list[ContractDefect] = []
    for defect in sorted(defects):
        if defect not in seen:
            seen.append(defect)
    return tuple(seen)


class ContractError(ValueError):
    """One or more structured shape/build defects."""

    def __init__(self, defects) -> None:
        self.defects: tuple[ContractDefect, ...] = _sorted_unique(defects)
        summary = "; ".join(f"{d.path}:{d.code}" for d in self.defects) or "no defects"
        super().__init__(f"contract violated: {summary}")


class VerificationContextError(ValueError):
    """Evaluation-graph verification could not resolve or recompute cleanly."""

    def __init__(self, defects) -> None:
        self.defects: tuple[ContractDefect, ...] = _sorted_unique(defects)
        summary = "; ".join(f"{d.path}:{d.code}" for d in self.defects) or "no defects"
        super().__init__(f"verification context invalid: {summary}")


class ArtifactConflictError(ValueError):
    """A create-only artifact write collided with different existing bytes."""

    def __init__(self, path: str, message: str) -> None:
        self.path = path
        super().__init__(message)
