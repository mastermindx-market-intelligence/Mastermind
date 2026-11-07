"""Pure responsibility intent normalization; no authority or lifecycle state.

This is the role syntax owned by Executive admission. Routing and preparation
may normalize it before admission, but a role never grants tools, a model,
children, or a Runtime binding. Lifecycle phase remains a separate input.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

SCHEMA = "mastermind.responsibility_intent/v1"
ROLES = frozenset({"principal", "sub_orchestrator", "operator", "worker"})
MODES = frozenset({"execute", "coordinate"})
_PHASES = frozenset({"plan", "work", "review", "repair", "aggregation"})
_KEYS = frozenset({"schema_version", "responsibility_role", "execution_mode"})


class ResponsibilityIntentError(ValueError):
    """Unsupported or inconsistent role syntax, before any execution effect."""


@dataclass(frozen=True)
class ResponsibilityIntent:
    responsibility_role: str
    execution_mode: str

    def __post_init__(self) -> None:
        if type(self.responsibility_role) is not str or type(self.execution_mode) is not str:
            raise ResponsibilityIntentError("role and mode must be plain strings")
        role = self.responsibility_role
        if role == "sub-orchestrator":
            role = "sub_orchestrator"
        if role not in ROLES:
            raise ResponsibilityIntentError("unknown responsibility role")
        if self.execution_mode not in MODES:
            raise ResponsibilityIntentError("unknown execution mode")
        if role == "worker" and self.execution_mode != "execute":
            raise ResponsibilityIntentError("worker cannot coordinate")
        object.__setattr__(self, "responsibility_role", role)

    def to_dict(self) -> dict[str, str]:
        return {"schema_version": SCHEMA,
                "responsibility_role": self.responsibility_role,
                "execution_mode": self.execution_mode}

    @property
    def digest(self) -> str:
        raw = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()

    def require_phase(self, phase: str) -> None:
        """Check intent/phase coherence, never authorize that phase or children."""
        if type(phase) is not str or phase not in _PHASES:
            raise ResponsibilityIntentError("unknown lifecycle phase")
        coordinating = phase in {"plan", "aggregation"}
        if coordinating != (self.execution_mode == "coordinate"):
            raise ResponsibilityIntentError("execution mode does not match lifecycle phase")


def normalize_responsibility_intent(value: object) -> ResponsibilityIntent:
    """Normalize one closed JSON object without interpreting grants or task classes."""
    if type(value) is not dict or set(value) != _KEYS:
        raise ResponsibilityIntentError("role intent must be an exact closed object")
    if type(value["schema_version"]) is not str or value["schema_version"] != SCHEMA:
        raise ResponsibilityIntentError("unsupported role intent version")
    return ResponsibilityIntent(value["responsibility_role"], value["execution_mode"])
