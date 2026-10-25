"""Closed request shape for the single Hermes delegation tool."""
from __future__ import annotations

import re
from typing import Any, Mapping


CHILD_KINDS = frozenset({"implementation", "watcher", "computer_use"})
CARRIERS = frozenset({"fabric", "cursor_cloud"})
TASK_CLASSES = frozenset({"mechanical", "fix_build", "review", "census", "audit"})
COMPLEXITIES = frozenset({
    "C0_MECHANICAL",
    "C1_ROUTINE_BOUNDED",
    "C2_COMPLEX_BOUNDED",
})
ACTIONS = frozenset({"submit", "status", "cancel", "review", "consume"})
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{7,127}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
SECRET_RE = re.compile(
    r"(?i)(api[_-]?key\s*[:=]|BEGIN [A-Z ]*PRIVATE KEY|sk-[A-Za-z0-9]|ghp_|xox[baprs]-|bearer\s+[A-Za-z0-9])"
)
MAX_OBJECTIVE = 4000
MAX_ACCEPTANCE = 1000
MAX_CONSTRAINTS = 8
MAX_CONSTRAINT = 300

FIXED_CONSTRAINTS = (
    "no_local_actuation",
    "built_in_hermes_delegation_disabled",
    "no_carrier_rehome",
    "unknown_effect_is_not_retried",
)


class SubmissionError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _text(value: Any, field: str, limit: int) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise SubmissionError(f"{field.upper()}_INVALID")
    if len(value) > limit:
        raise SubmissionError(f"{field.upper()}_INVALID")
    if SECRET_RE.search(value):
        raise SubmissionError("SECRET_MATERIAL_REFUSED")
    return value


def parse_submission(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise SubmissionError("ARGUMENTS_NOT_OBJECT")
    key = raw.get("idempotency_key")
    if not isinstance(key, str) or KEY_RE.fullmatch(key) is None:
        raise SubmissionError("IDEMPOTENCY_KEY_INVALID")
    replay_of = raw.get("replay_of")
    if replay_of is not None and (not isinstance(replay_of, str) or KEY_RE.fullmatch(replay_of) is None):
        raise SubmissionError("REPLAY_TARGET_INVALID")
    child_kind = raw.get("child_kind")
    if child_kind not in CHILD_KINDS:
        raise SubmissionError("CHILD_KIND_INVALID")
    carrier = raw.get("carrier")
    if carrier not in CARRIERS:
        raise SubmissionError("CARRIER_INVALID")
    task_class = raw.get("task_class")
    if task_class not in TASK_CLASSES:
        raise SubmissionError("TASK_CLASS_INVALID")
    complexity = raw.get("task_complexity")
    if complexity not in COMPLEXITIES:
        raise SubmissionError("TASK_COMPLEXITY_INVALID")
    if complexity == "C3_FRONTIER_JUDGMENT":
        raise SubmissionError("FRONTIER_STAYS_WITH_PARENT")
    parent_id = raw.get("parent_id")
    root_id = raw.get("root_id")
    if not isinstance(parent_id, str) or ID_RE.fullmatch(parent_id) is None:
        raise SubmissionError("PARENT_ID_INVALID")
    if not isinstance(root_id, str) or ID_RE.fullmatch(root_id) is None:
        raise SubmissionError("ROOT_ID_INVALID")
    if parent_id == key or root_id == key:
        raise SubmissionError("CHILD_CANNOT_BE_ITS_OWN_PARENT")
    objective = _text(raw.get("objective"), "objective", MAX_OBJECTIVE)
    acceptance = _text(raw.get("acceptance"), "acceptance", MAX_ACCEPTANCE)
    constraints = raw.get("constraints")
    if (
        not isinstance(constraints, list)
        or not constraints
        or len(constraints) > MAX_CONSTRAINTS
        or any(not isinstance(item, str) for item in constraints)
    ):
        raise SubmissionError("CONSTRAINTS_INVALID")
    clean_constraints = tuple(_text(item, "constraints", MAX_CONSTRAINT) for item in constraints)
    # Caller prose cannot drop the bridge's own bounds.
    merged = tuple(dict.fromkeys((*clean_constraints, *FIXED_CONSTRAINTS)))
    return {
        "idempotency_key": key,
        "replay_of": replay_of,
        "parent_id": parent_id,
        "root_id": root_id,
        "child_kind": child_kind,
        "carrier": carrier,
        "task_class": task_class,
        "task_complexity": complexity,
        "objective": objective,
        "acceptance": acceptance,
        "constraints": merged,
    }
