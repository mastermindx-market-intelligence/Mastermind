"""Deterministic material-change projection for Mastermind Context Fabric.

This module compares two already-scoped context identities. It does not discover scope,
read canonical owners, decide authority, mutate state, or broaden relevance. The caller
must supply only exact dependencies selected by existing owner/Context Fabric logic.

A change outside the supplied dependency closure is therefore intentionally invisible
to this projector. That is the feature: materiality follows the task closure, not the
size or movement of the entire Mastermind estate.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

from control_plane.session_truth_contract import canonical_json

SNAPSHOT_SCHEMA = "mastermind.context_materiality_snapshot.v1"
DIFF_SCHEMA = "mastermind.context_materiality_diff.v1"
MAX_OWNER_DIGESTS = 32
MAX_SOURCE_REFS = 4096
MAX_OVERLAYS = 64
MAX_COLLISIONS = 512
MAX_RETURNS = 512

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ContextMaterialityError(ValueError):
    """Materiality input is malformed or attempts to exceed a closed bound."""


def _string(value: object, label: str, *, maximum: int = 4096) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\x00" in value
        or len(value.encode("utf-8")) > maximum
    ):
        raise ContextMaterialityError(f"{label} is invalid")
    return value


def _digest(value: object, label: str, *, allow_sha40: bool = False) -> str:
    item = _string(value, label, maximum=64)
    if _HEX64.fullmatch(item):
        return item
    if allow_sha40 and _HEX40.fullmatch(item):
        return item
    raise ContextMaterialityError(f"{label} is invalid")


def _sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _mapping_rows(
    value: object,
    *,
    label: str,
    maximum: int,
    required_keys: frozenset[str],
) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ContextMaterialityError(f"{label} must be a sequence")
    if len(value) > maximum:
        raise ContextMaterialityError(f"{label} exceeds count bound")
    rows: list[Mapping[str, Any]] = []
    for row in value:
        if not isinstance(row, Mapping) or set(row) != required_keys:
            raise ContextMaterialityError(f"{label} row shape is invalid")
        rows.append(row)
    return rows


def _owner_digests(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping) or len(value) > MAX_OWNER_DIGESTS:
        raise ContextMaterialityError("owner_digests is invalid")
    result: dict[str, str] = {}
    for raw_owner, raw_digest in value.items():
        owner = _string(raw_owner, "owner", maximum=64)
        digest = _digest(raw_digest, f"owner digest {owner}", allow_sha40=True)
        if owner in result:
            raise ContextMaterialityError("owner_digests contains duplicate owner")
        result[owner] = digest
    return dict(sorted(result.items()))


def _source_refs(value: object) -> list[dict[str, str]]:
    rows = _mapping_rows(
        value,
        label="source_refs",
        maximum=MAX_SOURCE_REFS,
        required_keys=frozenset({"identity", "kind", "digest"}),
    )
    result: list[dict[str, str]] = []
    identities: set[str] = set()
    for row in rows:
        identity = _string(row["identity"], "source identity")
        kind = _string(row["kind"], "source kind", maximum=64)
        digest = _digest(row["digest"], "source digest", allow_sha40=True)
        if identity in identities:
            raise ContextMaterialityError("source_refs contains duplicate identity")
        identities.add(identity)
        result.append({"identity": identity, "kind": kind, "digest": digest})
    result.sort(key=lambda row: (row["kind"], row["identity"]))
    return result


def _overlays(value: object) -> list[dict[str, str]]:
    rows = _mapping_rows(
        value,
        label="workspace_overlays",
        maximum=MAX_OVERLAYS,
        required_keys=frozenset({"operation_id", "generation"}),
    )
    result: list[dict[str, str]] = []
    identities: set[str] = set()
    for row in rows:
        operation_id = _string(row["operation_id"], "workspace operation", maximum=256)
        generation = _digest(row["generation"], "workspace generation")
        if operation_id in identities:
            raise ContextMaterialityError(
                "workspace_overlays contains duplicate operation"
            )
        identities.add(operation_id)
        result.append({"operation_id": operation_id, "generation": generation})
    result.sort(key=lambda row: row["operation_id"])
    return result


def _collision_refs(value: object) -> list[dict[str, str]]:
    rows = _mapping_rows(
        value,
        label="collision_refs",
        maximum=MAX_COLLISIONS,
        required_keys=frozenset({"identity", "revision"}),
    )
    result: list[dict[str, str]] = []
    identities: set[str] = set()
    for row in rows:
        identity = _string(row["identity"], "collision identity")
        revision = _digest(row["revision"], "collision revision", allow_sha40=True)
        if identity in identities:
            raise ContextMaterialityError("collision_refs contains duplicate identity")
        identities.add(identity)
        result.append({"identity": identity, "revision": revision})
    result.sort(key=lambda row: row["identity"])
    return result


def _return_refs(value: object) -> list[dict[str, str]]:
    rows = _mapping_rows(
        value,
        label="return_refs",
        maximum=MAX_RETURNS,
        required_keys=frozenset({"identity", "digest"}),
    )
    result: list[dict[str, str]] = []
    identities: set[str] = set()
    for row in rows:
        identity = _string(row["identity"], "return identity")
        digest = _digest(row["digest"], "return digest")
        if identity in identities:
            raise ContextMaterialityError("return_refs contains duplicate identity")
        identities.add(identity)
        result.append({"identity": identity, "digest": digest})
    result.sort(key=lambda row: row["identity"])
    return result


def build_materiality_snapshot(
    *,
    task_digest: str,
    procedure_sha: str,
    owner_digests: Mapping[str, str],
    source_refs: Sequence[Mapping[str, str]],
    workspace_overlays: Sequence[Mapping[str, str]] = (),
    collision_refs: Sequence[Mapping[str, str]] = (),
    return_refs: Sequence[Mapping[str, str]] = (),
) -> dict[str, Any]:
    """Build one bounded exact-dependency snapshot.

    The snapshot contains no timestamp. Identical selected dependencies produce
    identical bytes regardless of unrelated estate observations.
    """

    normalized = {
        "task_digest": _digest(task_digest, "task_digest"),
        "procedure_sha": _digest(procedure_sha, "procedure_sha", allow_sha40=True),
        "owner_digests": _owner_digests(owner_digests),
        "source_refs": _source_refs(source_refs),
        "workspace_overlays": _overlays(workspace_overlays),
        "collision_refs": _collision_refs(collision_refs),
        "return_refs": _return_refs(return_refs),
    }
    generation = _sha256(normalized)
    return {
        "schema": SNAPSHOT_SCHEMA,
        "authoritative": False,
        "derived_read_only": True,
        **normalized,
        "generation": generation,
    }


def _validate_snapshot(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping) or value.get("schema") != SNAPSHOT_SCHEMA:
        raise ContextMaterialityError("snapshot schema is invalid")
    if (
        value.get("authoritative") is not False
        or value.get("derived_read_only") is not True
    ):
        raise ContextMaterialityError("snapshot authority boundary is invalid")
    supplied_generation = _digest(value.get("generation"), "snapshot generation")
    rebuilt = build_materiality_snapshot(
        task_digest=value.get("task_digest"),
        procedure_sha=value.get("procedure_sha"),
        owner_digests=value.get("owner_digests"),
        source_refs=value.get("source_refs"),
        workspace_overlays=value.get("workspace_overlays"),
        collision_refs=value.get("collision_refs"),
        return_refs=value.get("return_refs"),
    )
    if rebuilt["generation"] != supplied_generation:
        raise ContextMaterialityError("snapshot generation is invalid")
    return rebuilt


def _index(rows: Sequence[Mapping[str, str]], key: str) -> dict[str, Mapping[str, str]]:
    return {str(row[key]): row for row in rows}


def _append_changes(
    result: list[dict[str, Any]],
    *,
    before: Mapping[str, Mapping[str, str]],
    after: Mapping[str, Mapping[str, str]],
    revision_key: str,
    changed_code: str,
    added_code: str,
    removed_code: str,
    owner: str,
) -> None:
    for identity in sorted(set(before) | set(after)):
        old = before.get(identity)
        new = after.get(identity)
        if old is None:
            result.append(
                {
                    "code": added_code,
                    "identity": identity,
                    "owner": owner,
                    "before_revision": None,
                    "after_revision": new[revision_key],
                }
            )
        elif new is None:
            result.append(
                {
                    "code": removed_code,
                    "identity": identity,
                    "owner": owner,
                    "before_revision": old[revision_key],
                    "after_revision": None,
                }
            )
        elif old[revision_key] != new[revision_key]:
            result.append(
                {
                    "code": changed_code,
                    "identity": identity,
                    "owner": owner,
                    "before_revision": old[revision_key],
                    "after_revision": new[revision_key],
                }
            )


def diff_materiality(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> dict[str, Any]:
    """Return typed invalidators between two exact dependency snapshots."""

    left = _validate_snapshot(before)
    right = _validate_snapshot(after)
    invalidators: list[dict[str, Any]] = []

    if left["task_digest"] != right["task_digest"]:
        invalidators.append(
            {
                "code": "TASK_CHANGED",
                "identity": "task",
                "owner": "caller",
                "before_revision": left["task_digest"],
                "after_revision": right["task_digest"],
            }
        )
    if left["procedure_sha"] != right["procedure_sha"]:
        invalidators.append(
            {
                "code": "PROCEDURE_CHANGED",
                "identity": "protected-skillpack",
                "owner": "github",
                "before_revision": left["procedure_sha"],
                "after_revision": right["procedure_sha"],
            }
        )

    owners = sorted(set(left["owner_digests"]) | set(right["owner_digests"]))
    for owner in owners:
        old = left["owner_digests"].get(owner)
        new = right["owner_digests"].get(owner)
        if old != new:
            invalidators.append(
                {
                    "code": "OWNER_CONTEXT_CHANGED",
                    "identity": f"owner:{owner}",
                    "owner": owner,
                    "before_revision": old,
                    "after_revision": new,
                }
            )

    _append_changes(
        invalidators,
        before=_index(left["source_refs"], "identity"),
        after=_index(right["source_refs"], "identity"),
        revision_key="digest",
        changed_code="RELEVANT_SOURCE_CHANGED",
        added_code="RELEVANT_SOURCE_ADDED",
        removed_code="RELEVANT_SOURCE_REMOVED",
        owner="source-owner",
    )
    _append_changes(
        invalidators,
        before=_index(left["workspace_overlays"], "operation_id"),
        after=_index(right["workspace_overlays"], "operation_id"),
        revision_key="generation",
        changed_code="WORKSPACE_OVERLAY_CHANGED",
        added_code="WORKSPACE_OVERLAY_ADDED",
        removed_code="WORKSPACE_OVERLAY_REMOVED",
        owner="mmx-workspace",
    )
    _append_changes(
        invalidators,
        before=_index(left["collision_refs"], "identity"),
        after=_index(right["collision_refs"], "identity"),
        revision_key="revision",
        changed_code="COLLISION_SET_CHANGED",
        added_code="COLLISION_ADDED",
        removed_code="COLLISION_REMOVED",
        owner="github",
    )
    _append_changes(
        invalidators,
        before=_index(left["return_refs"], "identity"),
        after=_index(right["return_refs"], "identity"),
        revision_key="digest",
        changed_code="MATERIAL_RETURN_CHANGED",
        added_code="MATERIAL_RETURN_RECEIVED",
        removed_code="MATERIAL_RETURN_REMOVED",
        owner="return-owner",
    )

    priority = {
        "TASK_CHANGED": 0,
        "PROCEDURE_CHANGED": 10,
        "OWNER_CONTEXT_CHANGED": 20,
        "RELEVANT_SOURCE_CHANGED": 30,
        "RELEVANT_SOURCE_ADDED": 30,
        "RELEVANT_SOURCE_REMOVED": 30,
        "WORKSPACE_OVERLAY_CHANGED": 40,
        "WORKSPACE_OVERLAY_ADDED": 40,
        "WORKSPACE_OVERLAY_REMOVED": 40,
        "COLLISION_SET_CHANGED": 50,
        "COLLISION_ADDED": 50,
        "COLLISION_REMOVED": 50,
        "MATERIAL_RETURN_RECEIVED": 60,
        "MATERIAL_RETURN_CHANGED": 60,
        "MATERIAL_RETURN_REMOVED": 60,
    }
    invalidators.sort(
        key=lambda row: (
            priority.get(row["code"], 999),
            row["code"],
            row["identity"],
        )
    )
    mode = (
        "FULL_RECOVERY"
        if any(
            item["code"] in {"TASK_CHANGED", "PROCEDURE_CHANGED"}
            for item in invalidators
        )
        else "DELTA_RECOVERY"
    )
    return {
        "schema": DIFF_SCHEMA,
        "authoritative": False,
        "derived_read_only": True,
        "before_generation": left["generation"],
        "after_generation": right["generation"],
        "material_change": bool(invalidators),
        "recovery_mode": mode,
        "invalidators": invalidators,
    }
