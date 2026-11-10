"""Compose the existing T3 handoff/client inputs with the shared project view.

No runner, connection, new brief schema, identity store or dispatch loop. The
caller supplies the actual project, assigned source ref and permitted write scope.
"""
from __future__ import annotations

import json
from pathlib import PurePosixPath
from urllib.parse import urlparse

from .long_horizon_guidance import render_context
from .project_task_context import PlanContextError
from .t3_web_client import HandoffBrief, MAX_MESSAGE_BYTES


def handoff(context: dict, *, request_id: str, project_id: str, source_ref: str,
            allowed_write_paths: tuple[str, ...] = (), worktree_base: str | None = None) -> HandoffBrief:
    """Use the incumbent immutable brief; a source plan never grants write scope."""
    text = render_context(context)
    if type(source_ref) is not str:
        raise PlanContextError("T3_PLAN_SOURCE_PATH_MISMATCH")
    parsed = urlparse(source_ref)
    parts = parsed.path.split("/")
    if len(parts) < 6 or "/".join(parts[5:]) != context["source_path"]:
        raise PlanContextError("T3_PLAN_SOURCE_PATH_MISMATCH")
    if type(allowed_write_paths) is not tuple:
        raise PlanContextError("T3_PLAN_WRITE_SCOPE_INVALID")
    for value in allowed_write_paths:
        if type(value) is not str or not any(
                value == parent or PurePosixPath(parent) in PurePosixPath(value).parents
                for parent in context["allowed_paths"]):
            raise PlanContextError("T3_PLAN_WRITE_SCOPE_EXPANDED")
    return HandoffBrief(request_id=request_id, project_id=project_id, objective=text,
        source_ref=source_ref, allowed_write_paths=allowed_write_paths, worktree_base=worktree_base,
        acceptance_checks=(
            "Retain every source requirement and stable task identity; execute one dependency-ready principal task.",
            "Verify the focused task against its exact acceptance criteria; read off-focus detail at the bound source.",
            "Save observed evidence, read back, then reassess the whole parent outcome. A turn or todo completion is not acceptance.",
        ),
        stop_conditions=(
            "Respect actual native stop, permission, budget, source-contract and pending-input boundaries.",
            "Reconcile an uncertain original effect without duplicate send, replacement thread or provider fallback.",
        ),
        non_goals=tuple(context["non_goals"]))


def followup(context: dict, *, user_direction: str, direction_kind: str) -> str:
    """Retain current plan context beside one explicit queued-turn direction.

    This formats a message for the existing T3CliClient.send on its original
    ThreadReceipt. It does not implement live steering or amend the source plan.
    Pause/stop require actual native control, never a message queued behind work.
    """
    if type(direction_kind) is not str or direction_kind not in {"side_question", "refinement", "add_requirement", "replace_scope", "pause", "stop"}:
        raise PlanContextError("DIRECTION_KIND_INVALID")
    if direction_kind in {"pause", "stop"}:
        raise PlanContextError("T3_NATIVE_CONTROL_REQUIRED")
    try:
        valid = type(user_direction) is str and bool(user_direction.strip()) and len(user_direction.encode("utf-8")) <= 4096
    except UnicodeError:
        valid = False
    if not valid:
        raise PlanContextError("T3_DIRECTION_INVALID")
    text = render_context(context) + "\nCurrent direction, not a new permission:\n" + json.dumps(
        {"kind": direction_kind, "text": user_direction, "source_plan_amended": False}, ensure_ascii=True)
    if len(text.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise PlanContextError("T3_PLAN_MESSAGE_TOO_LARGE")
    return text
