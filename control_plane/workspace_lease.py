"""Rev5 WorkspaceLease records inside the workspace/resource owner family.

Attach point: the existing workspace/resource owner seam in this package --
``control_plane.workspace_resource_capacity`` (retained-capacity composition),
``control_plane.mission_workspace`` (T3 workspace lifecycle) and
``control_plane.workspace_source_operations`` (returned patch/commit path).
This module is standalone: ``workspace_lease_attach(path)`` opens its own
SQLite file so the broker/workspace owner can persist company leases beside
its existing records.

Ownership boundary: T3 owns the actual workspace lifecycle. The company lease
records ownership and eligibility only. Reclamation is an explicit eligibility
computation over settled state; no filesystem mutation of any kind happens in
this module and there is no second deletion sweeper here. Lease expiry alone
never establishes reclamation safety.

Placement hierarchy (Rev5 section 4):
  1. one managed repo/object cache per host;
  2. read-only analysis on an EXACT revision snapshot, no mutable worktree;
  3. one integration checkout = ONE writer (same-seam workers return scoped
     patches or get sequential writer leases);
  4. truly independent concurrent writers get BOUNDED isolated worktrees;
  5. cross-host workers use host-local checkouts at the assigned base
     revision and return patches/commits via the existing return path -- no
     live shared writable checkout over NFS.

Under disk pressure: stop new writer allocations, drain known owners, reclaim
what is eligible, and preserve active or uncertain allocations.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from typing import Any

HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")

KIND_SINGLE_WRITER = "single_writer"
KIND_ISOLATED_WORKTREE = "isolated_worktree"
KIND_READ_SNAPSHOT = "read_snapshot"
KIND_HOST_CACHE = "host_cache"

WRITER_KINDS = (KIND_SINGLE_WRITER, KIND_ISOLATED_WORKTREE)
STATUS_ACTIVE = "active"
STATUS_RELEASED = "released"

RETENTION_CLEAN = "CLEAN"
RETENTION_DIRTY_RETAINED = "DIRTY_RETAINED"
RETENTION_DIRTY = "DIRTY"

RECLAIM_RETENTION_STATES = (RETENTION_CLEAN, RETENTION_DIRTY_RETAINED)

DEFAULT_ISOLATED_WORKTREE_CAP = 4
_ISOLATED_CAP_ENV = "MMOS_WORKSPACE_ISOLATED_WORKTREE_CAP"
_MAX_TEXT = 512
_MAX_REVISION = 40


class WorkspaceLeaseConflict(ValueError):
    """Precise conflict carrying the blocking writer identity when present."""

    def __init__(self, reason: str, **details: Any) -> None:
        super().__init__(f"WORKSPACE_LEASE_CONFLICT:{reason}")
        self.reason = reason
        self.details = {key: value for key, value in details.items() if value is not None}

    def as_dict(self) -> dict[str, Any]:
        return {"reason": self.reason} | dict(self.details)


def _text(value: Any, name: str) -> str:
    if type(value) is not str or not value or len(value) > _MAX_TEXT or value != value.strip():
        raise WorkspaceLeaseConflict("INVALID_VALUE", field=name)
    return value


def _revision(value: Any, name: str = "base_revision") -> str:
    if type(value) is not str or HEX40.fullmatch(value) is None:
        raise WorkspaceLeaseConflict("INVALID_VALUE", field=name)
    return value


def _digest_text(value: Any, name: str) -> str:
    if value in (None, ""):
        return ""
    if type(value) is not str or HEX64.fullmatch(value) is None:
        raise WorkspaceLeaseConflict("INVALID_VALUE", field=name)
    return value


def _optional_text(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _text(value, name)


def _int_count(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        raise WorkspaceLeaseConflict("INVALID_VALUE", field=name)
    return value


def _refs(value: Any, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if type(value) is not tuple and type(value) is not list:
        raise WorkspaceLeaseConflict("INVALID_VALUE", field=name)
    return tuple(_text(item, name) for item in value)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


@dataclasses.dataclass(frozen=True)
class WorkspaceLeaseRecord:
    """One company workspace lease (Rev5 section 4, record field list).

    ``t3_workspace_id`` is a nullable join field only. The T3 lane fills it
    later for real workspaces; this module never fabricates a value: an
    acquire that is not given one stores ``None``.
    """

    repo_ref: str
    host_ref: str
    native_workspace_owner: str
    workspace_ref: str
    base_revision: str
    writer_ref: str | None
    writer_epoch: int | None
    active_assignment_refs: tuple[str, ...]
    reserved_scratch_bytes: int
    observed_bytes: int
    retention_state: str
    result_artifact_refs: tuple[str, ...]
    lease_kind: str
    lease_id: str
    native_activity_settled: bool
    unresolved_effects: bool
    lease_status: str = STATUS_ACTIVE
    t3_workspace_id: str | None = None
    source_scope_digest: str = ""
    cache_key: str | None = None
    expires_ms: int | None = None
    created_ms: int = 0
    updated_ms: int = 0
    released_ms: int | None = None


def attach_workspace_lease(
    binding: Any, record: WorkspaceLeaseRecord, *, now_ms: int
) -> Any:
    """Stamp an ``ExecutionBinding``'s v1.1 workspace-containment block from
    one REAL lease record (Rev 5 §4 / change order §3E join; Director C).

    The join is by contract, not by copy: the binding's ``workspace_ref``,
    ``base_ref``, ``writer_epoch`` and ``lease_ref`` BECOME the lease's
    values, so a launch carried by this binding is contained by exactly the
    workspace lease the workspace authority issued — a drifted binding or
    lease fails the equality checks downstream instead of silently widening
    containment. ``t3_workspace_id`` stays a lease-side native join field
    (this module never fabricates it): the T3 lane fills it when the real
    native workspace exists, and the binding reaches it through
    ``lease_ref``. The binding is returned as a NEW record (input
    unchanged). Refusals (REVIEW_C_E_OPUS_20261109 A3), all typed
    ``WorkspaceLeaseConflict``:

    * ``LEASE_NOT_ACTIVE`` — the lease is not ``active``;
    * ``LEASE_EXPIRED`` — an active lease whose ``expires_ms`` is at or
      before the injected ``now_ms`` (module time convention: callers pass
      epoch-ms; ``expires_ms=None`` never expires);
    * ``LEASE_ASSIGNMENT_MISMATCH`` — the lease's ``active_assignment_refs``
      do not name the binding's ``attempt_ref`` (a lease with no assignment
      contains nobody);
    * ``LEASE_REBIND_REFUSED`` — the binding already carries containment
      (any of ``lease_ref``/``workspace_ref``/``base_ref``/``writer_epoch``)
      that differs from this lease: a DIFFERENT lease, or the same
      ``lease_ref`` with drifted values. Re-attaching the SAME lease is
      idempotent.
    """
    from control_plane.child_execution_contracts import ExecutionBinding

    if not isinstance(binding, ExecutionBinding):
        raise WorkspaceLeaseConflict(
            "BINDING_TYPE_INVALID", field=type(binding).__name__
        )
    if not isinstance(record, WorkspaceLeaseRecord):
        raise WorkspaceLeaseConflict(
            "LEASE_TYPE_INVALID", field=type(record).__name__
        )
    if type(now_ms) is not int or now_ms < 0:
        raise WorkspaceLeaseConflict("INVALID_VALUE", field="now_ms")
    if record.lease_status != STATUS_ACTIVE:
        raise WorkspaceLeaseConflict(
            "LEASE_NOT_ACTIVE", lease_id=record.lease_id,
            lease_status=record.lease_status,
        )
    if record.expires_ms is not None and record.expires_ms <= now_ms:
        raise WorkspaceLeaseConflict(
            "LEASE_EXPIRED", lease_id=record.lease_id,
            expires_ms=record.expires_ms, now_ms=now_ms,
        )
    if binding.attempt_ref not in record.active_assignment_refs:
        raise WorkspaceLeaseConflict(
            "LEASE_ASSIGNMENT_MISMATCH", lease_id=record.lease_id,
            attempt_ref=binding.attempt_ref or None,
            active_assignment_refs=list(record.active_assignment_refs),
        )
    joined = dataclasses.replace(
        binding,
        workspace_ref=record.workspace_ref,
        base_ref=record.base_revision,
        writer_epoch=record.writer_epoch,
        lease_ref=record.lease_id,
    )
    already_contained = bool(
        binding.lease_ref or binding.workspace_ref or binding.base_ref
        or binding.writer_epoch is not None
    )
    if already_contained and binding != joined:
        raise WorkspaceLeaseConflict(
            "LEASE_REBIND_REFUSED", lease_id=record.lease_id,
            bound_lease_ref=binding.lease_ref,
        )
    return joined


def host_cache_key(*, lockfiles: list[str], platform: str, toolchain: str) -> str:
    """Key for the per-host managed repo/object cache.

    Cache identity reflects lockfiles, platform and toolchain so a host never
    shares one cache body across incompatible dependency resolutions.
    """
    entries = {"lockfiles": [str(item) for item in lockfiles],
               "platform": _text(platform, "platform"),
               "toolchain": _text(toolchain, "toolchain")}
    return hashlib.sha256(_canonical(entries)).hexdigest()


class WorkspaceLeaseStore:
    """SQLite-backed store of workspace ownership/eligibility records.

    One writer for a mutable ``single_writer`` checkout is enforced atomically:
    the guard runs inside ``BEGIN IMMEDIATE`` and a UNIQUE partial index backs
    it up, so a second acquire gets a precise conflict carrying the current
    writer ref and epoch -- never a silent takeover.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(path, timeout=30.0, isolation_level=None,
                                           check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA busy_timeout=10000")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS workspace_leases (
                lease_id TEXT PRIMARY KEY,
                lease_kind TEXT NOT NULL,
                lease_status TEXT NOT NULL,
                repo_ref TEXT NOT NULL,
                host_ref TEXT NOT NULL,
                native_workspace_owner TEXT NOT NULL,
                workspace_ref TEXT NOT NULL,
                base_revision TEXT NOT NULL,
                writer_ref TEXT,
                writer_epoch INTEGER,
                active_assignment_refs TEXT NOT NULL,
                reserved_scratch_bytes INTEGER NOT NULL,
                observed_bytes INTEGER NOT NULL,
                retention_state TEXT NOT NULL,
                result_artifact_refs TEXT NOT NULL,
                t3_workspace_id TEXT,
                source_scope_digest TEXT NOT NULL DEFAULT '',
                cache_key TEXT,
                native_activity_settled INTEGER NOT NULL DEFAULT 0,
                unresolved_effects INTEGER NOT NULL DEFAULT 0,
                expires_ms INTEGER,
                created_ms INTEGER NOT NULL,
                updated_ms INTEGER NOT NULL,
                released_ms INTEGER
            );
            CREATE INDEX IF NOT EXISTS workspace_leases_repo_host
                ON workspace_leases(repo_ref, host_ref);
            CREATE INDEX IF NOT EXISTS workspace_leases_workspace
                ON workspace_leases(workspace_ref);
            CREATE UNIQUE INDEX IF NOT EXISTS workspace_leases_single_writer_active
                ON workspace_leases(repo_ref, host_ref)
                WHERE lease_kind='single_writer' AND lease_status='active';
            CREATE UNIQUE INDEX IF NOT EXISTS workspace_leases_host_cache
                ON workspace_leases(repo_ref, host_ref)
                WHERE lease_kind='host_cache';
            """
        )

    def close(self) -> None:
        self._connection.close()

    # -- internal helpers ------------------------------------------------

    def _statement(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._connection.execute(sql, params)

    def _row_to_record(self, row: sqlite3.Row) -> WorkspaceLeaseRecord:
        return WorkspaceLeaseRecord(
            repo_ref=row["repo_ref"],
            host_ref=row["host_ref"],
            native_workspace_owner=row["native_workspace_owner"],
            workspace_ref=row["workspace_ref"],
            base_revision=row["base_revision"],
            writer_ref=row["writer_ref"],
            writer_epoch=row["writer_epoch"],
            active_assignment_refs=tuple(json.loads(row["active_assignment_refs"])),
            reserved_scratch_bytes=row["reserved_scratch_bytes"],
            observed_bytes=row["observed_bytes"],
            retention_state=row["retention_state"],
            result_artifact_refs=tuple(json.loads(row["result_artifact_refs"])),
            lease_kind=row["lease_kind"],
            lease_id=row["lease_id"],
            native_activity_settled=bool(row["native_activity_settled"]),
            unresolved_effects=bool(row["unresolved_effects"]),
            lease_status=row["lease_status"],
            t3_workspace_id=row["t3_workspace_id"],
            source_scope_digest=row["source_scope_digest"],
            cache_key=row["cache_key"],
            expires_ms=row["expires_ms"],
            created_ms=row["created_ms"],
            updated_ms=row["updated_ms"],
            released_ms=row["released_ms"],
        )

    def _lease_id(self, record: dict[str, Any]) -> str:
        seed = record | {"nonce": time.time_ns()}
        return hashlib.sha256(_canonical(seed)).hexdigest()

    def _retention(self, value: Any) -> str:
        if value not in (RETENTION_CLEAN, RETENTION_DIRTY_RETAINED, RETENTION_DIRTY):
            raise WorkspaceLeaseConflict("INVALID_RETENTION_STATE", retention_state=value)
        return value

    def _pressure_refusal(self) -> None:
        if self.allocations_blocked:
            raise WorkspaceLeaseConflict("ALLOCATIONS_BLOCKED_DISK_PRESSURE")

    def _insert(self, record_row: dict[str, Any]) -> WorkspaceLeaseRecord:
        self._statement(
            "INSERT INTO workspace_leases "
            "(lease_id, lease_kind, lease_status, repo_ref, host_ref, native_workspace_owner,"
            " workspace_ref, base_revision, writer_ref, writer_epoch, active_assignment_refs,"
            " reserved_scratch_bytes, observed_bytes, retention_state, result_artifact_refs,"
            " t3_workspace_id, source_scope_digest, cache_key, native_activity_settled,"
            " unresolved_effects, expires_ms, created_ms, updated_ms, released_ms)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                record_row["lease_id"], record_row["lease_kind"], record_row["lease_status"],
                record_row["repo_ref"], record_row["host_ref"], record_row["native_workspace_owner"],
                record_row["workspace_ref"], record_row["base_revision"], record_row["writer_ref"],
                record_row["writer_epoch"], _canonical(list(record_row["active_assignment_refs"])).decode(),
                record_row["reserved_scratch_bytes"], record_row["observed_bytes"],
                record_row["retention_state"], _canonical(list(record_row["result_artifact_refs"])).decode(),
                record_row["t3_workspace_id"], record_row["source_scope_digest"],
                record_row["cache_key"], int(record_row["native_activity_settled"]),
                int(record_row["unresolved_effects"]), record_row["expires_ms"],
                record_row["created_ms"], record_row["updated_ms"], record_row["released_ms"],
            ),
        )
        return self.read(record_row["lease_id"])  # type: ignore[return-value]

    # -- hierarchy 3: one writer per mutable integration checkout --------

    def acquire_single_writer(self, *, repo_ref, host_ref, native_workspace_owner,
                              workspace_ref, base_revision, writer_ref,
                              active_assignment_refs=(), reserved_scratch_bytes=0,
                              observed_bytes=0, result_artifact_refs=(),
                              t3_workspace_id=None, source_scope_digest="",
                              retention_state=RETENTION_CLEAN,
                              now_ms, expires_ms=None) -> WorkspaceLeaseRecord:
        """Take THE writer lease for one mutable checkout at (repo, host).

        Same-seam workers that cannot take this lease must return scoped
        patches through the existing return path or wait for a sequential
        writer lease; this call never takes over silently.
        """
        repo_ref = _text(repo_ref, "repo_ref")
        host_ref = _text(host_ref, "host_ref")
        owner = _text(native_workspace_owner, "native_workspace_owner")
        workspace_ref = _text(workspace_ref, "workspace_ref")
        base_revision = _revision(base_revision)
        writer_ref = _text(writer_ref, "writer_ref")
        assignments = _refs(active_assignment_refs, "active_assignment_refs")
        _int_count(reserved_scratch_bytes, "reserved_scratch_bytes")
        _int_count(observed_bytes, "observed_bytes")
        artifacts = _refs(result_artifact_refs, "result_artifact_refs")
        t3_workspace_id = _optional_text(t3_workspace_id, "t3_workspace_id")
        source_scope_digest = _digest_text(source_scope_digest, "source_scope_digest")
        self._retention(retention_state)
        self._pressure_refusal()
        if type(now_ms) is not int or now_ms < 0:
            raise WorkspaceLeaseConflict("INVALID_VALUE", field="now_ms")
        if expires_ms is not None and (type(expires_ms) is not int or expires_ms <= 0):
            raise WorkspaceLeaseConflict("INVALID_VALUE", field="expires_ms")
        with self._lock:
            self._statement("BEGIN IMMEDIATE")
            try:
                held = self._statement(
                    "SELECT * FROM workspace_leases WHERE repo_ref=? AND host_ref=?"
                    " AND lease_kind='single_writer' AND lease_status='active'",
                    (repo_ref, host_ref),
                ).fetchone()
                if held is not None:
                    raise WorkspaceLeaseConflict(
                        "SINGLE_WRITER_ALREADY_HELD",
                        repo_ref=repo_ref, host_ref=host_ref,
                        writer_ref=held["writer_ref"], writer_epoch=held["writer_epoch"],
                        workspace_ref=held["workspace_ref"],
                    )
                prior = self._statement(
                    "SELECT MAX(COALESCE(writer_epoch,0)) AS top FROM workspace_leases"
                    " WHERE repo_ref=? AND host_ref=? AND lease_kind='single_writer'",
                    (repo_ref, host_ref),
                ).fetchone()
                epoch = int(prior["top"] or 0) + 1
                row = {
                    "lease_id": self._lease_id({"kind": KIND_SINGLE_WRITER, "repo_ref": repo_ref,
                                                "host_ref": host_ref, "workspace_ref": workspace_ref,
                                                "writer_ref": writer_ref, "writer_epoch": epoch,
                                                "created_ms": now_ms}),
                    "lease_kind": KIND_SINGLE_WRITER, "lease_status": STATUS_ACTIVE,
                    "repo_ref": repo_ref, "host_ref": host_ref, "native_workspace_owner": owner,
                    "workspace_ref": workspace_ref, "base_revision": base_revision,
                    "writer_ref": writer_ref, "writer_epoch": epoch,
                    "active_assignment_refs": assignments,
                    "reserved_scratch_bytes": reserved_scratch_bytes,
                    "observed_bytes": observed_bytes, "retention_state": retention_state,
                    "result_artifact_refs": artifacts, "t3_workspace_id": t3_workspace_id,
                    "source_scope_digest": source_scope_digest, "cache_key": None,
                    "native_activity_settled": False, "unresolved_effects": False,
                    "expires_ms": expires_ms, "created_ms": now_ms, "updated_ms": now_ms,
                    "released_ms": None,
                }
                try:
                    return self._insert(row)
                except sqlite3.IntegrityError:
                    held = self._statement(
                        "SELECT * FROM workspace_leases WHERE repo_ref=? AND host_ref=?"
                        " AND lease_kind='single_writer' AND lease_status='active'",
                        (repo_ref, host_ref),
                    ).fetchone()
                    if held is None:
                        raise
                    raise WorkspaceLeaseConflict(
                        "SINGLE_WRITER_ALREADY_HELD",
                        repo_ref=repo_ref, host_ref=host_ref,
                        writer_ref=held["writer_ref"], writer_epoch=held["writer_epoch"],
                        workspace_ref=held["workspace_ref"],
                    ) from None
            finally:
                self._statement("COMMIT")

    # -- hierarchy 4: bounded isolated worktrees -------------------------

    def isolated_worktree_cap(self) -> int:
        raw = os.environ.get(_ISOLATED_CAP_ENV)
        if raw is None:
            return DEFAULT_ISOLATED_WORKTREE_CAP
        if not raw.isdigit() or int(raw) < 1:
            raise WorkspaceLeaseConflict("INVALID_ISOLATED_WORKTREE_CAP", configured=raw)
        return int(raw)

    def acquire_isolated_worktree(self, *, repo_ref, host_ref, native_workspace_owner,
                                  workspace_ref, base_revision, writer_ref,
                                  active_assignment_refs=(), reserved_scratch_bytes=0,
                                  observed_bytes=0, result_artifact_refs=(),
                                  t3_workspace_id=None, source_scope_digest="",
                                  retention_state=RETENTION_CLEAN,
                                  now_ms, expires_ms=None) -> WorkspaceLeaseRecord:
        """Take one bounded isolated worktree lease for an independent writer.

        Bounded per (repo_ref, host_ref). Over the cap this refuses with a
        precise reason instead of silently widening the boundary.
        """
        repo_ref = _text(repo_ref, "repo_ref")
        host_ref = _text(host_ref, "host_ref")
        owner = _text(native_workspace_owner, "native_workspace_owner")
        workspace_ref = _text(workspace_ref, "workspace_ref")
        base_revision = _revision(base_revision)
        writer_ref = _text(writer_ref, "writer_ref")
        assignments = _refs(active_assignment_refs, "active_assignment_refs")
        _int_count(reserved_scratch_bytes, "reserved_scratch_bytes")
        _int_count(observed_bytes, "observed_bytes")
        artifacts = _refs(result_artifact_refs, "result_artifact_refs")
        t3_workspace_id = _optional_text(t3_workspace_id, "t3_workspace_id")
        source_scope_digest = _digest_text(source_scope_digest, "source_scope_digest")
        self._retention(retention_state)
        self._pressure_refusal()
        if type(now_ms) is not int or now_ms < 0:
            raise WorkspaceLeaseConflict("INVALID_VALUE", field="now_ms")
        if expires_ms is not None and (type(expires_ms) is not int or expires_ms <= 0):
            raise WorkspaceLeaseConflict("INVALID_VALUE", field="expires_ms")
        cap = self.isolated_worktree_cap()
        with self._lock:
            self._statement("BEGIN IMMEDIATE")
            try:
                count_row = self._statement(
                    "SELECT COUNT(*) AS n FROM workspace_leases WHERE repo_ref=? AND host_ref=?"
                    " AND lease_kind='isolated_worktree' AND lease_status='active'",
                    (repo_ref, host_ref),
                ).fetchone()
                active_count = int(count_row["n"])
                if active_count >= cap:
                    raise WorkspaceLeaseConflict(
                        "ISOLATED_WORKTREE_CAP_EXCEEDED",
                        repo_ref=repo_ref, host_ref=host_ref,
                        active_isolated_worktrees=active_count, cap=cap,
                    )
                row = {
                    "lease_id": self._lease_id({"kind": KIND_ISOLATED_WORKTREE,
                                                "repo_ref": repo_ref, "host_ref": host_ref,
                                                "workspace_ref": workspace_ref,
                                                "writer_ref": writer_ref, "created_ms": now_ms}),
                    "lease_kind": KIND_ISOLATED_WORKTREE, "lease_status": STATUS_ACTIVE,
                    "repo_ref": repo_ref, "host_ref": host_ref, "native_workspace_owner": owner,
                    "workspace_ref": workspace_ref, "base_revision": base_revision,
                    "writer_ref": writer_ref, "writer_epoch": None,
                    "active_assignment_refs": assignments,
                    "reserved_scratch_bytes": reserved_scratch_bytes,
                    "observed_bytes": observed_bytes, "retention_state": retention_state,
                    "result_artifact_refs": artifacts, "t3_workspace_id": t3_workspace_id,
                    "source_scope_digest": source_scope_digest, "cache_key": None,
                    "native_activity_settled": False, "unresolved_effects": False,
                    "expires_ms": expires_ms, "created_ms": now_ms, "updated_ms": now_ms,
                    "released_ms": None,
                }
                return self._insert(row)
            finally:
                self._statement("COMMIT")

    # -- hierarchy 2: read-only exact-revision snapshots -----------------

    def register_read_snapshot(self, *, repo_ref, host_ref, native_workspace_owner,
                               workspace_ref, base_revision, source_scope_digest="",
                               t3_workspace_id=None, now_ms, expires_ms=None) -> WorkspaceLeaseRecord:
        """Record a read-only analysis lease on the EXACT base revision.

        Readers never take, wait on or conflict with the writer lease, and
        multiple readers on the same snapshot revision are fine. Read-only
        snapshot registration reserves no dirty scratch capacity, so it stays
        available under disk pressure.
        """
        repo_ref = _text(repo_ref, "repo_ref")
        host_ref = _text(host_ref, "host_ref")
        owner = _text(native_workspace_owner, "native_workspace_owner")
        workspace_ref = _text(workspace_ref, "workspace_ref")
        base_revision = _revision(base_revision)
        source_scope_digest = _digest_text(source_scope_digest, "source_scope_digest")
        t3_workspace_id = _optional_text(t3_workspace_id, "t3_workspace_id")
        if type(now_ms) is not int or now_ms < 0:
            raise WorkspaceLeaseConflict("INVALID_VALUE", field="now_ms")
        if expires_ms is not None and (type(expires_ms) is not int or expires_ms <= 0):
            raise WorkspaceLeaseConflict("INVALID_VALUE", field="expires_ms")
        with self._lock:
            row = {
                "lease_id": self._lease_id({"kind": KIND_READ_SNAPSHOT, "repo_ref": repo_ref,
                                            "host_ref": host_ref, "workspace_ref": workspace_ref,
                                            "base_revision": base_revision, "created_ms": now_ms}),
                "lease_kind": KIND_READ_SNAPSHOT, "lease_status": STATUS_ACTIVE,
                "repo_ref": repo_ref, "host_ref": host_ref, "native_workspace_owner": owner,
                "workspace_ref": workspace_ref, "base_revision": base_revision,
                "writer_ref": None, "writer_epoch": None, "active_assignment_refs": (),
                "reserved_scratch_bytes": 0, "observed_bytes": 0,
                "retention_state": RETENTION_CLEAN, "result_artifact_refs": (),
                "t3_workspace_id": t3_workspace_id, "source_scope_digest": source_scope_digest,
                "cache_key": None, "native_activity_settled": True,
                "unresolved_effects": False, "expires_ms": expires_ms,
                "created_ms": now_ms, "updated_ms": now_ms, "released_ms": None,
            }
            self._statement("BEGIN IMMEDIATE")
            try:
                return self._insert(row)
            finally:
                self._statement("COMMIT")

    # -- hierarchy 1: per-host managed repo/object cache ------------------

    def register_host_cache(self, *, repo_ref, host_ref, lockfiles, platform, toolchain,
                            observed_bytes=0, t3_workspace_id=None, now_ms) -> WorkspaceLeaseRecord:
        """Record (or refresh) the host-managed repo/object cache lease.

        One managed cache per (repo_ref, host_ref); re-registration refreshes
        the cache key derived from lockfiles/platform/toolchain instead of
        duplicating the record.
        """
        repo_ref = _text(repo_ref, "repo_ref")
        host_ref = _text(host_ref, "host_ref")
        if type(lockfiles) is not list or any(type(item) is not str for item in lockfiles):
            raise WorkspaceLeaseConflict("INVALID_VALUE", field="lockfiles")
        cache_key = host_cache_key(lockfiles=lockfiles, platform=platform, toolchain=toolchain)
        _int_count(observed_bytes, "observed_bytes")
        t3_workspace_id = _optional_text(t3_workspace_id, "t3_workspace_id")
        if type(now_ms) is not int or now_ms < 0:
            raise WorkspaceLeaseConflict("INVALID_VALUE", field="now_ms")
        with self._lock:
            self._statement("BEGIN IMMEDIATE")
            try:
                existing = self._statement(
                    "SELECT lease_id FROM workspace_leases WHERE repo_ref=? AND host_ref=?"
                    " AND lease_kind='host_cache'",
                    (repo_ref, host_ref),
                ).fetchone()
                if existing is not None:
                    self._statement(
                        "UPDATE workspace_leases SET cache_key=?, observed_bytes=?,"
                        " updated_ms=?, lease_status=? WHERE lease_id=?",
                        (cache_key, observed_bytes, now_ms, STATUS_ACTIVE, existing["lease_id"]),
                    )
                    return self.read(existing["lease_id"])  # type: ignore[return-value]
                row = {
                    "lease_id": self._lease_id({"kind": KIND_HOST_CACHE, "repo_ref": repo_ref,
                                                "host_ref": host_ref, "cache_key": cache_key,
                                                "created_ms": now_ms}),
                    "lease_kind": KIND_HOST_CACHE, "lease_status": STATUS_ACTIVE,
                    "repo_ref": repo_ref, "host_ref": host_ref,
                    "native_workspace_owner": _K_HOST_CACHE_OWNER,
                    "workspace_ref": f"host-cache:{repo_ref}:{host_ref}",
                    "base_revision": _NEVER_MUTABLE_REVISION,
                    "writer_ref": None, "writer_epoch": None, "active_assignment_refs": (),
                    "reserved_scratch_bytes": 0, "observed_bytes": observed_bytes,
                    "retention_state": RETENTION_CLEAN, "result_artifact_refs": (),
                    "t3_workspace_id": t3_workspace_id, "source_scope_digest": "",
                    "cache_key": cache_key, "native_activity_settled": True,
                    "unresolved_effects": False, "expires_ms": None,
                    "created_ms": now_ms, "updated_ms": now_ms, "released_ms": None,
                }
                return self._insert(row)
            finally:
                self._statement("COMMIT")

    # -- lifecycle: renew / release / settle / observe ---------------------

    def renew(self, lease_id, *, writer_epoch=None, now_ms, expires_ms=None) -> WorkspaceLeaseRecord:
        """Extend a lease. A writer lease's epoch must match the live epoch."""
        lease_id = _text(lease_id, "lease_id")
        if type(now_ms) is not int or now_ms < 0:
            raise WorkspaceLeaseConflict("INVALID_VALUE", field="now_ms")
        row = self._statement("SELECT * FROM workspace_leases WHERE lease_id=?", (lease_id,)).fetchone()
        if row is None:
            raise WorkspaceLeaseConflict("LEASE_NOT_FOUND", lease_id=lease_id)
        if row["lease_kind"] in WRITER_KINDS:
            if type(writer_epoch) is not int:
                raise WorkspaceLeaseConflict("WRITER_EPOCH_REQUIRED", lease_id=lease_id,
                                             writer_ref=row["writer_ref"],
                                             writer_epoch=row["writer_epoch"])
            if int(row["writer_epoch"]) != writer_epoch:
                raise WorkspaceLeaseConflict("WRITER_EPOCH_MISMATCH", lease_id=lease_id,
                                             writer_ref=row["writer_ref"],
                                             writer_epoch=row["writer_epoch"],
                                             supplied_writer_epoch=writer_epoch)
        if row["lease_status"] != STATUS_ACTIVE:
            raise WorkspaceLeaseConflict("LEASE_NOT_ACTIVE", lease_id=lease_id,
                                         lease_status=row["lease_status"])
        held_expires = expires_ms if expires_ms is not None else row["expires_ms"]
        if held_expires is not None and (type(held_expires) is not int or held_expires <= 0):
            raise WorkspaceLeaseConflict("INVALID_VALUE", field="expires_ms")
        with self._lock:
            self._statement("BEGIN IMMEDIATE")
            try:
                self._statement(
                    "UPDATE workspace_leases SET expires_ms=?, updated_ms=? WHERE lease_id=?",
                    (held_expires, now_ms, lease_id),
                )
            finally:
                self._statement("COMMIT")
        return self.read(lease_id)  # type: ignore[return-value]

    def release(self, lease_id, *, writer_epoch=None, now_ms, retention_state=None,
                result_artifact_refs=None) -> WorkspaceLeaseRecord:
        """Release a lease. A stale epoch is refused with a precise conflict.

        Releasing a writer lease also records the retention posture required
        for later reclamation: necessary dirty output and returned artifacts
        are retained on the record, never touched on disk here.
        """
        lease_id = _text(lease_id, "lease_id")
        if type(now_ms) is not int or now_ms < 0:
            raise WorkspaceLeaseConflict("INVALID_VALUE", field="now_ms")
        row = self._statement("SELECT * FROM workspace_leases WHERE lease_id=?", (lease_id,)).fetchone()
        if row is None:
            raise WorkspaceLeaseConflict("LEASE_NOT_FOUND", lease_id=lease_id)
        if row["lease_status"] != STATUS_ACTIVE:
            raise WorkspaceLeaseConflict("LEASE_NOT_ACTIVE", lease_id=lease_id,
                                         lease_status=row["lease_status"])
        if row["lease_kind"] in WRITER_KINDS:
            if type(writer_epoch) is not int:
                raise WorkspaceLeaseConflict("WRITER_EPOCH_REQUIRED", lease_id=lease_id,
                                             writer_ref=row["writer_ref"],
                                             writer_epoch=row["writer_epoch"])
            if int(row["writer_epoch"]) != writer_epoch:
                raise WorkspaceLeaseConflict(
                    "STALE_WRITER_RELEASE", lease_id=lease_id,
                    writer_ref=row["writer_ref"], writer_epoch=row["writer_epoch"],
                    supplied_writer_epoch=writer_epoch)
        held_retention = row["retention_state"] if retention_state is None else self._retention(retention_state)
        if result_artifact_refs is not None:
            held_artifacts = _refs(result_artifact_refs, "result_artifact_refs")
        else:
            held_artifacts = tuple(json.loads(row["result_artifact_refs"]))
        with self._lock:
            self._statement("BEGIN IMMEDIATE")
            try:
                self._statement(
                    "UPDATE workspace_leases SET lease_status=?, released_ms=?, updated_ms=?,"
                    " retention_state=?, result_artifact_refs=? WHERE lease_id=?",
                    (STATUS_RELEASED, now_ms, now_ms, held_retention,
                     _canonical(list(held_artifacts)).decode(), lease_id),
                )
            finally:
                self._statement("COMMIT")
        return self.read(lease_id)  # type: ignore[return-value]

    def record_native_activity_settled(self, lease_id, *, now_ms) -> WorkspaceLeaseRecord:
        lease_id = _text(lease_id, "lease_id")
        return self._flag(lease_id, "native_activity_settled=1", now_ms)

    def record_effects_resolved(self, lease_id, *, now_ms) -> WorkspaceLeaseRecord:
        lease_id = _text(lease_id, "lease_id")
        return self._flag(lease_id, "unresolved_effects=0", now_ms)

    def _flag(self, lease_id: str, assignment: str, now_ms: int) -> WorkspaceLeaseRecord:
        row = self._statement("SELECT * FROM workspace_leases WHERE lease_id=?", (lease_id,)).fetchone()
        if row is None:
            raise WorkspaceLeaseConflict("LEASE_NOT_FOUND", lease_id=lease_id)
        with self._lock:
            self._statement("BEGIN IMMEDIATE")
            try:
                self._statement(
                    f"UPDATE workspace_leases SET {assignment}, updated_ms=? WHERE lease_id=?",
                    (now_ms, lease_id),
                )
            finally:
                self._statement("COMMIT")
        return self.read(lease_id)  # type: ignore[return-value]

    def observe_bytes(self, lease_id, *, observed_bytes, now_ms) -> WorkspaceLeaseRecord:
        lease_id = _text(lease_id, "lease_id")
        _int_count(observed_bytes, "observed_bytes")
        if type(now_ms) is not int or now_ms < 0:
            raise WorkspaceLeaseConflict("INVALID_VALUE", field="now_ms")
        row = self._statement("SELECT * FROM workspace_leases WHERE lease_id=?", (lease_id,)).fetchone()
        if row is None:
            raise WorkspaceLeaseConflict("LEASE_NOT_FOUND", lease_id=lease_id)
        with self._lock:
            self._statement("BEGIN IMMEDIATE")
            try:
                self._statement(
                    "UPDATE workspace_leases SET observed_bytes=?, updated_ms=? WHERE lease_id=?",
                    (observed_bytes, now_ms, lease_id),
                )
            finally:
                self._statement("COMMIT")
        return self.read(lease_id)  # type: ignore[return-value]

    # -- inspection -------------------------------------------------------

    def read(self, lease_id) -> WorkspaceLeaseRecord | None:
        lease_id = _text(lease_id, "lease_id")
        row = self._statement("SELECT * FROM workspace_leases WHERE lease_id=?", (lease_id,)).fetchone()
        return None if row is None else self._row_to_record(row)

    def active_single_writer(self, repo_ref, host_ref) -> WorkspaceLeaseRecord | None:
        repo_ref = _text(repo_ref, "repo_ref")
        host_ref = _text(host_ref, "host_ref")
        row = self._statement(
            "SELECT * FROM workspace_leases WHERE repo_ref=? AND host_ref=?"
            " AND lease_kind='single_writer' AND lease_status='active'",
            (repo_ref, host_ref),
        ).fetchone()
        return None if row is None else self._row_to_record(row)

    def inspect(self, *, repo_ref=None, host_ref=None, lease_kind=None,
                lease_status=None) -> list[WorkspaceLeaseRecord]:
        clauses, params = [], []
        if repo_ref is not None:
            clauses.append("repo_ref=?")
            params.append(_text(repo_ref, "repo_ref"))
        if host_ref is not None:
            clauses.append("host_ref=?")
            params.append(_text(host_ref, "host_ref"))
        if lease_kind is not None:
            clauses.append("lease_kind=?")
            params.append(_text(lease_kind, "lease_kind"))
        if lease_status is not None:
            clauses.append("lease_status=?")
            params.append(_text(lease_status, "lease_status"))
        sql = "SELECT * FROM workspace_leases"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_ms, lease_id"
        return [self._row_to_record(row) for row in self._statement(sql, tuple(params)).fetchall()]

    def active_writer_workspaces(self) -> set[str]:
        return {row["workspace_ref"] for row in self._statement(
            "SELECT workspace_ref FROM workspace_leases WHERE lease_kind IN (?,?)"
            " AND lease_status='active'",
            (KIND_SINGLE_WRITER, KIND_ISOLATED_WORKTREE),
        ).fetchall()}

    # -- disk-pressure posture -------------------------------------------

    @property
    def allocations_blocked(self) -> bool:
        return bool(getattr(self, "_allocations_blocked", False))

    def set_disk_pressure(self, disk_pressure: Any) -> None:
        if type(disk_pressure) is not bool:
            raise WorkspaceLeaseConflict("INVALID_VALUE", field="disk_pressure")
        self._allocations_blocked = disk_pressure

    # -- reclamation eligibility -----------------------------------------

    def reclaim_view(self, *, now_ms: int) -> list[dict[str, Any]]:
        """Assemble per-workspace eligibility inputs from stored leases only."""
        if type(now_ms) is not int or now_ms < 0:
            raise WorkspaceLeaseConflict("INVALID_VALUE", field="now_ms")
        live_writers = self.active_writer_workspaces()
        workspaces: dict[str, list[sqlite3.Row]] = {}
        for row in self._statement(
            "SELECT * FROM workspace_leases WHERE lease_kind!='host_cache'"
            " ORDER BY created_ms, lease_id"
        ).fetchall():
            workspaces.setdefault(row["workspace_ref"], []).append(row)
        view = []
        for workspace_ref, rows in workspaces.items():
            released_writer = None
            latest = None
            for row in rows:
                latest = row
                if row["lease_kind"] in WRITER_KINDS and row["lease_status"] == STATUS_RELEASED:
                    released_writer = row
            representative = released_writer if released_writer is not None else latest
            assignments = tuple(json.loads(representative["active_assignment_refs"]))
            view.append({
                "workspace_ref": workspace_ref,
                "repo_ref": representative["repo_ref"],
                "host_ref": representative["host_ref"],
                "retention_state": representative["retention_state"],
                "native_activity_settled": bool(representative["native_activity_settled"]),
                "unresolved_effects": bool(representative["unresolved_effects"]),
                "live_writer": workspace_ref in live_writers,
                "active_assignments": assignments,
                "expires_ms": representative["expires_ms"],
                "lease_expired": (representative["expires_ms"] is not None
                                  and representative["expires_ms"] <= now_ms),
            })
        return view


_K_HOST_CACHE_OWNER = "host-cache-owner"
# The host cache carries no mutable checkout, so it records the cache body's
# identity rather than any real Git revision; a fixed sentinel keeps the NOT
# NULL base_revision column honest without inventing a live revision.
_NEVER_MUTABLE_REVISION = "0" * 40


def reclaim_eligible(states, *, now_ms=None) -> dict[str, Any]:
    """Pure eligibility computation for reclaiming workspace allocations.

    Reclamation safety requires ALL of: settled native activity, no live
    writer, no unresolved effects and a retention state that retains the
    necessary dirty/untracked output (``CLEAN`` or ``DIRTY_RETAINED``), with
    no still-active assignments (preserve active or uncertain allocations).
    Lease expiry alone establishes nothing and is deliberately NOT part of
    the safety decision: expired-but-unsafe is refused and expired-but-safe
    is eligible on the same four conditions as unexpired.

    Accepts WorkspaceLeaseRecord instances or the dicts produced by
    ``WorkspaceLeaseStore.reclaim_view``. Performs no filesystem work of any
    kind; callers own any explicit reclamation outside this module.
    """
    if type(now_ms) is not int or now_ms < 0:
        raise WorkspaceLeaseConflict("INVALID_VALUE", field="now_ms")
    eligible = []
    ineligible = []
    for state in states:
        if isinstance(state, WorkspaceLeaseRecord):
            live_writer = (state.lease_kind in WRITER_KINDS
                           and state.lease_status == STATUS_ACTIVE)
            settled = state.native_activity_settled
            unresolved = state.unresolved_effects
            retention_state = state.retention_state
            active_assignments = state.active_assignment_refs
            workspace_ref = state.workspace_ref
            expired = (state.expires_ms is not None and state.expires_ms <= now_ms)
        elif isinstance(state, dict):
            live_writer = bool(state["live_writer"])
            settled = bool(state["native_activity_settled"])
            unresolved = bool(state["unresolved_effects"])
            retention_state = state["retention_state"]
            active_assignments = tuple(state.get("active_assignments", tuple()))
            workspace_ref = state["workspace_ref"]
            expired = bool(state.get("lease_expired", False))
        else:
            raise WorkspaceLeaseConflict("INVALID_VALUE", field="state")
        blocked = []
        if not settled:
            blocked.append("native_activity_not_settled")
        if live_writer:
            blocked.append("live_writer_present")
        if unresolved:
            blocked.append("unresolved_effects_present")
        if retention_state not in RECLAIM_RETENTION_STATES:
            blocked.append("retention_state_not_reclaimable")
        if active_assignments:
            blocked.append("active_assignments_present")
        entry = {"workspace_ref": workspace_ref, "retention_state": retention_state,
                 "lease_expired": expired}
        if blocked:
            ineligible.append(entry | {"blocked_by": blocked})
        else:
            eligible.append(entry | {"reasons": [
                "settled_native_activity", "no_live_writer", "no_unresolved_effects",
                f"retention_state:{retention_state}", "no_active_assignments"]})
    return {"eligible": eligible, "ineligible": ineligible}


def allocations_blocked_under_pressure(store: WorkspaceLeaseStore, *, disk_pressure: bool) -> dict[str, Any]:
    """Apply the disk-pressure posture and report the observed state.

    Sets the store's allocation block, computes what is reclaimable now, and
    preserves every active or uncertain allocation for the drain/review pass
    instead of assuming anything is safe.
    """
    store.set_disk_pressure(bool(disk_pressure))
    view = store.reclaim_view(now_ms=0)
    eligible = {entry["workspace_ref"] for entry in reclaim_eligible(view, now_ms=0)["eligible"]}
    preserved, reclaimable = [], []
    for entry in view:
        target = reclaimable if entry["workspace_ref"] in eligible else preserved
        target.append(entry["workspace_ref"])
    return {
        "allocations_blocked": bool(disk_pressure),
        "preserve_active_or_uncertain": preserved,
        "drain_candidates": reclaimable,
    }


def workspace_lease_attach(path: str) -> WorkspaceLeaseStore:
    """Attach a standalone lease store at ``path`` for the workspace owner.

    The broker/workspace owner can persist leases in its own SQLite file;
    the attach point on the owner seam is control_plane's
    workspace_resource_capacity family (see module docstring).
    """
    if type(path) is not str or not path:
        raise WorkspaceLeaseConflict("INVALID_VALUE", field="path")
    return WorkspaceLeaseStore(path)
