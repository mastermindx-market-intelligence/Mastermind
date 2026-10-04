"""Pure derived projection for one existing managed Mastermind workspace.

The overlay describes local source divergence for context retrieval. It is not workspace
custody, source authority, a lease, a writer registry, or proof that a model may modify
the workspace. The acquisition adapter must first prove the workspace through the
existing Git/mmx-workspace registration.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

from control_plane.session_truth_contract import canonical_json

OVERLAY_SCHEMA = "mastermind.workspace_context_overlay.v1"
MAX_CHANGES = 4096
_OPERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_LANE_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_STATUS_RE = re.compile(r"^[ MADRCUT?!]{1,2}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_CONTENT_STATES = {
    "HASHED",
    "DELETED",
    "SENSITIVE_PATH",
    "TOO_LARGE",
    "NON_REGULAR",
    "UNAVAILABLE",
    "COMMITTED_REF",
}


class WorkspaceContextOverlayError(ValueError):
    """A workspace observation cannot be projected without guessing."""


def _string(value: object, label: str, *, maximum: int = 4096) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\x00" in value
        or len(value.encode("utf-8")) > maximum
    ):
        raise WorkspaceContextOverlayError(f"{label} is invalid")
    return value


def _identity(
    *,
    operation_id: object,
    lane: object,
    base_sha: object,
    head_sha: object,
    branch: object,
) -> dict[str, str]:
    operation = _string(operation_id, "operation_id", maximum=96)
    selected_lane = _string(lane, "lane", maximum=32)
    base = _string(base_sha, "base_sha", maximum=40)
    head = _string(head_sha, "head_sha", maximum=40)
    selected_branch = _string(branch, "branch", maximum=256)
    if _OPERATION_RE.fullmatch(operation) is None:
        raise WorkspaceContextOverlayError("operation_id is invalid")
    if _LANE_RE.fullmatch(selected_lane) is None:
        raise WorkspaceContextOverlayError("lane is invalid")
    if _SHA_RE.fullmatch(base) is None or _SHA_RE.fullmatch(head) is None:
        raise WorkspaceContextOverlayError("Git identity is invalid")
    return {
        "operation_id": operation,
        "lane": selected_lane,
        "base_sha": base,
        "head_sha": head,
        "branch": selected_branch,
    }


def _change(row: object, *, working: bool) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise WorkspaceContextOverlayError("change row is invalid")
    allowed = {"status", "path", "path_digest", "content_sha256", "content_state"}
    if set(row) != allowed:
        raise WorkspaceContextOverlayError("change row shape is invalid")
    status = _string(row.get("status"), "change status", maximum=2)
    if _STATUS_RE.fullmatch(status) is None:
        raise WorkspaceContextOverlayError("change status is invalid")

    path = row.get("path")
    path_digest = row.get("path_digest")
    if (path is None) == (path_digest is None):
        raise WorkspaceContextOverlayError("change path identity is invalid")
    normalized_path: str | None = None
    normalized_path_digest: str | None = None
    if path is not None:
        normalized_path = _string(path, "change path")
        if normalized_path.startswith("/") or ".." in normalized_path.split("/"):
            raise WorkspaceContextOverlayError(
                "change path must be repository-relative"
            )
    else:
        normalized_path_digest = _string(path_digest, "path digest", maximum=64)
        if _DIGEST_RE.fullmatch(normalized_path_digest) is None:
            raise WorkspaceContextOverlayError("path digest is invalid")

    content_state = _string(row.get("content_state"), "content state", maximum=32)
    if content_state not in _CONTENT_STATES:
        raise WorkspaceContextOverlayError("content state is invalid")
    content_digest = row.get("content_sha256")
    if content_digest is not None:
        content_digest = _string(content_digest, "content digest", maximum=64)
        if _DIGEST_RE.fullmatch(content_digest) is None:
            raise WorkspaceContextOverlayError("content digest is invalid")
    if content_state == "HASHED" and content_digest is None:
        raise WorkspaceContextOverlayError("hashed content requires a digest")
    if not working and content_state not in {"COMMITTED_REF", "SENSITIVE_PATH"}:
        raise WorkspaceContextOverlayError("committed change content state is invalid")
    if content_state == "SENSITIVE_PATH" and normalized_path_digest is None:
        raise WorkspaceContextOverlayError("sensitive path must be opaque")

    return {
        "status": status,
        "path": normalized_path,
        "path_digest": normalized_path_digest,
        "content_sha256": content_digest,
        "content_state": content_state,
    }


def _changes(value: object, *, working: bool) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise WorkspaceContextOverlayError("changes must be a sequence")
    if len(value) > MAX_CHANGES:
        raise WorkspaceContextOverlayError("change count exceeds bound")
    rows = [_change(row, working=working) for row in value]
    rows.sort(
        key=lambda row: (
            row["path"] or "",
            row["path_digest"] or "",
            row["status"],
            row["content_state"],
        )
    )
    identities = [(row["path"], row["path_digest"], row["status"]) for row in rows]
    if len(identities) != len(set(identities)):
        raise WorkspaceContextOverlayError("changes contain duplicate identities")
    return rows


def build_workspace_overlay(
    *,
    operation_id: str,
    lane: str,
    base_sha: str,
    head_sha: str,
    branch: str,
    committed_changes: Sequence[Mapping[str, Any]],
    working_changes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build one deterministic, authority-neutral workspace overlay."""

    identity = _identity(
        operation_id=operation_id,
        lane=lane,
        base_sha=base_sha,
        head_sha=head_sha,
        branch=branch,
    )
    committed = _changes(committed_changes, working=False)
    working = _changes(working_changes, working=True)
    core = {
        **identity,
        "committed_changes": committed,
        "working_changes": working,
    }
    generation = hashlib.sha256(canonical_json(core).encode("utf-8")).hexdigest()
    safe_paths = sorted(
        {
            row["path"]
            for row in [*committed, *working]
            if isinstance(row.get("path"), str)
        }
    )
    sensitive_change_count = sum(
        1 for row in [*committed, *working] if row["content_state"] == "SENSITIVE_PATH"
    )
    return {
        "schema": OVERLAY_SCHEMA,
        "authoritative": False,
        "derived_read_only": True,
        "custody_owner": "mmx-workspace",
        **identity,
        "dirty": bool(working),
        "overlay_generation": generation,
        "safe_changed_paths": safe_paths,
        "sensitive_change_count": sensitive_change_count,
        "committed_changes": committed,
        "working_changes": working,
    }
