"""Bounded native child inventory through an injected, already-authorized MCP read.

The ordinary T3 CLI list deliberately excludes subagents. It is not sufficient
for team coverage. This module owns no connection, authentication, persistence,
watcher or lifecycle; it explicitly requests subagents from the existing owner.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import inspect
from typing import Any, Callable

from .t3_web_client import NativeUnavailable, _identity

SCHEMA = "mastermind.t3_native_child_inventory.v1"
MAX_THREADS = 1000
MAX_PAGES = 10
LIVE_STATES = frozenset({"preparing", "queued", "starting", "running", "waiting"})
STATES = LIVE_STATES | {"idle", "completed", "interrupted", "failed", "cancelled", "rolled_back"}


def _check(condition: bool) -> None:
    if not condition:
        raise NativeUnavailable("native child inventory is incomplete or unqualified")


def _time(value: str) -> datetime:
    _check(type(value) is str and len(value) <= 64)
    try:
        parsed = datetime.fromisoformat(value)
        _check(parsed.utcoffset() is not None)
        return parsed
    except (ValueError, TypeError):
        raise NativeUnavailable("native inventory timestamp is unqualified") from None


@dataclass(frozen=True, slots=True)
class InventoryThread:
    thread_id: str
    parent_thread_id: str | None
    relationship_to_parent: str | None
    status: str
    latest_run_id: str | None

    def __post_init__(self) -> None:
        _identity(self.thread_id, "thread_id")
        if self.parent_thread_id is not None:
            _identity(self.parent_thread_id, "parent_thread_id")
        if self.latest_run_id is not None:
            _identity(self.latest_run_id, "latest_run_id")
        _check(self.parent_thread_id != self.thread_id)
        _check(type(self.status) is str and self.status in STATES)
        _check(self.relationship_to_parent is None or
               (type(self.relationship_to_parent) is str and self.relationship_to_parent in {"fork", "subagent"}))
        _check((self.parent_thread_id is None) == (self.relationship_to_parent is None))


@dataclass(frozen=True, slots=True)
class NativeInventory:
    environment_id: str
    project_id: str
    threads: tuple[InventoryThread, ...]
    observed_at: str

    def __post_init__(self) -> None:
        _identity(self.environment_id, "environment_id")
        _identity(self.project_id, "project_id")
        _time(self.observed_at)
        _check(type(self.threads) is tuple and len(self.threads) <= MAX_THREADS
               and all(type(item) is InventoryThread for item in self.threads))
        by_id = {item.thread_id: item for item in self.threads}
        _check(len(by_id) == len(self.threads))
        for item in self.threads:
            seen = set()
            current = item.thread_id
            while current in by_id:
                _check(current not in seen)
                seen.add(current)
                current = by_id[current].parent_thread_id

    def is_fresh(self, *, now: datetime | None = None, max_age_seconds: int = 120) -> bool:
        now = now or datetime.now(timezone.utc)
        age = (now - _time(self.observed_at)).total_seconds()
        return 0 <= age <= max_age_seconds

    def descendants(self, root_thread_id: str) -> frozenset[str]:
        _check(root_thread_id in {item.thread_id for item in self.threads})
        found = {root_thread_id}
        while True:
            next_ids = {item.thread_id for item in self.threads
                        if item.relationship_to_parent == "subagent" and item.parent_thread_id in found}
            if next_ids <= found:
                return frozenset(found)
            found.update(next_ids)

    def document(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "environment_id": self.environment_id, "project_id": self.project_id,
                "threads": [asdict(item) for item in self.threads], "observed_at": self.observed_at,
                "includes_subagents": True, "complete_paginated_read": True,
                "scope": "environment_local_project_threads", "atomic_snapshot": False}


def inventory_from_document(value: Any) -> NativeInventory:
    _check(type(value) is dict and set(value) == {
        "schema", "environment_id", "project_id", "threads", "observed_at", "includes_subagents",
        "complete_paginated_read", "scope", "atomic_snapshot"})
    _check(value["schema"] == SCHEMA and value["includes_subagents"] is True
           and value["complete_paginated_read"] is True and value["atomic_snapshot"] is False
           and value["scope"] == "environment_local_project_threads")
    _check(type(value["threads"]) is list and len(value["threads"]) <= MAX_THREADS)
    fields = {"thread_id", "parent_thread_id", "relationship_to_parent", "status", "latest_run_id"}
    _check(all(type(row) is dict and set(row) == fields for row in value["threads"]))
    try:
        return NativeInventory(value["environment_id"], value["project_id"],
                               tuple(InventoryThread(**row) for row in value["threads"]), value["observed_at"])
    except (TypeError, ValueError):
        raise NativeUnavailable("native child inventory document is unqualified") from None


async def read_native_inventory(call_native: Callable[..., Any], *, environment_id: str,
                                project_id: str) -> NativeInventory:
    """Consume the native MCP result shape, paging exactly once per cursor.

    The callable must return the existing native tool's structured success value.
    It owns transport/auth/error-envelope decoding. No credentials are accepted.
    Omit environmentId: that field means linked-environment forwarding, whereas
    this adapter reads the caller's already-bound local environment only.
    """
    _identity(environment_id, "environment_id")
    _identity(project_id, "project_id")
    _check(callable(call_native))
    rows: list[InventoryThread] = []
    cursor, total = 0, None
    try:
        for _ in range(MAX_PAGES):
            value = call_native("t3_thread_list", {"projectId": project_id, "includeSubagents": True,
                                                   "limit": 100, "cursor": cursor})
            if inspect.isawaitable(value):
                value = await value
            _check(type(value) is dict and value.get("projectId") == project_id
                   and type(value.get("threads")) is list and len(value["threads"]) <= 100
                   and type(value.get("total")) is int and 0 <= value["total"] <= MAX_THREADS
                   and "nextCursor" in value)
            total = value["total"] if total is None else total
            _check(value["total"] == total)
            for row in value["threads"]:
                _check(type(row) is dict and row.get("projectId") == project_id
                       and {"threadId", "parentThreadId", "relationshipToParent", "status", "latestRunId"} <= row.keys())
                rows.append(InventoryThread(row["threadId"], row["parentThreadId"], row["relationshipToParent"],
                                            row["status"], row["latestRunId"]))
            next_cursor = value["nextCursor"]
            _check(len(rows) <= total)
            if next_cursor is None:
                _check(len(rows) == total)
                return NativeInventory(environment_id, project_id, tuple(rows), datetime.now(timezone.utc).isoformat())
            _check(type(next_cursor) is int and next_cursor > cursor and bool(value["threads"]))
            cursor = next_cursor
    except NativeUnavailable:
        raise
    except Exception:
        raise NativeUnavailable("native child inventory read unavailable") from None
    raise NativeUnavailable("native child inventory exceeded bounded pagination")
