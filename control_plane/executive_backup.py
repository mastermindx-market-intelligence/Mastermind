"""Verified backup and offline restore for the Executive SQLite authority store.

The SQLite online-backup API is the only supported way to create a backup while
the Executive service is running.  Backup manifests contain hashes and schema
attestations only: they never contain table rows, lease tokens, or other runtime
payloads.

Restores are deliberately offline operations.  The caller must coordinate with
the Executive service through the same owner-only marker and advisory lock used
by the service.  A fully verified database is staged on the target filesystem,
then atomically replaces the live database.  The previous database and any WAL
sidecars are retained as an owner-only rollback set; a failed post-swap
verification automatically restores that set.
"""

from __future__ import annotations

import dataclasses
import fcntl
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import ExitStack, contextmanager, nullcontext
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote
from uuid import uuid4

from control_plane.executive_runtime import (
    _MIGRATIONS,
    _DB_RELATIVE_PATH,
    DEFAULT_BUSY_TIMEOUT_MS,
    _migration_checksum,
    SCHEMA_VERSION,
    PersistenceError,
    Runtime,
    RuntimeProofError,
    RuntimeStore,
)

BACKUP_MANIFEST_SCHEMA_VERSION = "mastermind.executive_backup_manifest/v1"
DEFAULT_SERVICE_MARKER_NAME = "executive-service.running"
DEFAULT_SERVICE_LOCK_NAME = "executive-service.lock"
_MAX_MANIFEST_BYTES = 64 * 1024
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_BACKUP_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")
LEGACY_CONTENT_PROJECTION_SCHEMA = (
    "mastermind.executive_legacy_content_projection/v1"
)
_LEGACY_TABLE_COLUMNS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("workers", ("worker_id", "provider", "account_label", "worker_type", "identity_status", "metadata_json", "last_seen_at_ms", "created_at_ms", "updated_at_ms", "version"), ("worker_id",)),
    ("worker_quota_classes", ("worker_id", "quota_class", "status", "provider", "model", "effort", "cost_class", "capabilities_json", "metadata_json", "held_attempt_id", "fence_counter", "last_seen_at_ms", "created_at_ms", "updated_at_ms", "version"), ("worker_id", "quota_class")),
    ("jobs", ("job_id", "objective", "department", "priority", "status", "assigned_worker_id", "assigned_quota_class", "current_attempt_id", "authority_level", "branch", "worktree", "constraints_json", "requested_authorities_json", "authority_policy_hash", "allowed_write_paths_json", "validation_commands_json", "checkpoint_json", "result_json", "attempt_count", "attempt_limit", "available_at_ms", "cancel_requested_at_ms", "created_at_ms", "updated_at_ms", "version", "parent_job_id", "root_job_id", "depth", "owner_seat", "escalation_target", "business_impact", "review_required", "reviews_job_id"), ("job_id",)),
    ("attempts", ("attempt_id", "job_id", "attempt_number", "worker_id", "quota_class", "status", "fence_generation", "authority_policy_hash", "lease_token", "lease_owner", "lease_expires_at_ms", "heartbeat_at_ms", "checkpoint_sequence", "checkpoint_json", "result_json", "error_json", "pid", "pgid", "process_start_identity", "boot_id", "provider_session_id", "stdout_path", "stderr_path", "result_path", "exit_code", "launch_metadata_json", "started_at_ms", "finished_at_ms", "created_at_ms", "updated_at_ms", "version", "execution_mode", "requested_execution_profile_json", "requested_execution_profile_digest"), ("attempt_id",)),
    ("events", ("event_id", "aggregate_type", "aggregate_id", "sequence", "event_type", "command_id", "actor", "job_id", "attempt_id", "worker_id", "quota_class", "payload_json", "created_at_ms"), ("event_id",)),
    ("sqlite_sequence", ("name", "seq"), ("name",)),
    ("harness_session_epochs", ("session_epoch_id", "attempt_id", "worker_id", "epoch_number", "provider_session_id", "state", "created_at_ms", "ended_at_ms", "abandonment_class"), ("session_epoch_id",)),
    ("process_generations", ("process_generation_id", "session_epoch_id", "worker_id", "provider_session_id", "generation_number", "pid", "pgid", "process_start_identity", "boot_id", "started_at_ms", "last_observed_at_ms", "ended_at_ms", "termination_class", "exit_code", "executive_writer_held", "provider_writer_state", "observed_attestation_json", "observed_attestation_digest", "created_at_ms"), ("process_generation_id",)),
)
_V4_JOB_COLUMNS = ("orchestration_role", "orchestration_provenance_json", "orchestration_provenance_digest", "plan_attempt_id", "plan_digest", "plan_step_id", "repair_round", "supersedes_job_id")
_V4_ATTEMPT_COLUMNS = ("effective_grant_json", "effective_grant_digest", "placement_snapshot_json", "placement_snapshot_digest", "execution_principal_snapshot_json", "execution_principal_snapshot_digest")
_NORMALIZED_SCHEMA_DIGESTS = {
    3: "4d20a48aee0a47b568f7ec49cf67d5e8a4f9a42217088462b370e6e753d23c92",
    4: "56054e6e64ca6e69e878ce6488bb5527e1051212db94bae0fbf625eed78ca6a4",
    5: "b2fe4455306b2bdcf4f698d958e420e4f885e941dc1f0b8db602cbb39edcedbd",
    6: "4ed21db1880afe43bdab58ea07da335c2db60a218ccdedee44eaefd1d2175c05",
    7: "7692d62bd4126dd6fcaec2873ee9506a1faac96b3246684366e1dfa6e34c6a87",
}
# Full-v4 content preservation: the same eight retained tables as the closed
# v1-v3 projection, but carrying every v4 column (including the v4-only
# orchestration/grant/placement/principal fields) so the v4->v5 transition can
# prove byte-exact preservation where the historical projection is blind.
FULL_V4_CONTENT_PROJECTION_SCHEMA = (
    "mastermind.executive_full_v4_content_projection/v1"
)
_FULL_V4_TABLE_COLUMNS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = tuple(
    (
        name,
        (*columns, *_V4_JOB_COLUMNS)
        if name == "jobs"
        else (*columns, *_V4_ATTEMPT_COLUMNS)
        if name == "attempts"
        else columns,
        primary_key,
    )
    for name, columns, primary_key in _LEGACY_TABLE_COLUMNS
)

FULL_V5_CONTENT_PROJECTION_SCHEMA = (
    "mastermind.executive_full_v5_content_projection/v1"
)
FULL_V6_CONTENT_PROJECTION_SCHEMA = (
    "mastermind.executive_full_v6_content_projection/v1"
)
PHYSICAL_HISTORY_PROJECTION_SCHEMA = (
    "mastermind.executive_physical_history_projection/v1"
)
_PHYSICAL_HISTORY_TABLE_COLUMNS = (
    (
        "physical_resource_commitments",
        (
            "commitment_id", "host_id", "operation_key", "phase_key", "owner_id",
            "carrier_id", "allocation_generation", "revision", "state",
            "request_fingerprint", "bundle_fingerprint", "bundle_manifest_json",
            "caller_binding_json", "source_binding_json", "policy_binding_json",
            "pool_binding_json", "phase_scope_json", "decision_event_id",
            "begin_event_id", "last_observation_event_id", "settlement_event_id",
            "created_at_ms", "updated_at_ms",
        ),
        ("commitment_id",),
    ),
    (
        "physical_resource_demands",
        (
            "commitment_id", "allocation_generation", "dimension", "capacity_pool_id",
            "window_binding_json", "qualified_incremental_peak", "remaining_charge",
            "attributed_materialized_or_active", "attribution_json", "observed_revision",
        ),
        ("commitment_id", "allocation_generation", "dimension", "capacity_pool_id"),
    ),
    _LEGACY_TABLE_COLUMNS[4],  # All columns of every physical Event, including refusals.
)
_PHYSICAL_EVENT_PREDICATE = (
    "aggregate_type='physical_resource_operation' "
    "OR event_type GLOB 'PHYSICAL_RESOURCE_*'"
)

UPGRADE_BARRIER_SCHEMA = "mastermind.executive_schema_upgrade_barrier/v1"
RESTORE_BARRIER_SCHEMA = "mastermind.executive_restore_barrier/v1"
UPGRADE_PREFLIGHT_SCHEMA = "mastermind.executive_schema_upgrade_preflight/v1"
UPGRADE_COMPLETION_SCHEMA = "mastermind.executive_schema_upgrade_completion/v1"
UPGRADE_CENSUS_SCHEMA = "mastermind.executive_schema_upgrade_quiesce/v1"
_UPGRADE_BARRIER_NAME = "executive-schema-upgrade.in-progress.json"
_UPGRADE_PREFLIGHT_NAME = "executive-schema-upgrade.preflight.json"
_UPGRADE_COMPLETION_NAME = "executive-schema-upgrade.completion.json"
_UPGRADE_V4_TO_V5_PREFLIGHT_NAME = "executive-schema-upgrade.v4-to-v5.preflight.json"
_UPGRADE_V4_TO_V5_COMPLETION_NAME = "executive-schema-upgrade.v4-to-v5.completion.json"
_UPGRADE_V5_TO_V6_PREFLIGHT_NAME = "executive-schema-upgrade.v5-to-v6.preflight.json"
_UPGRADE_V5_TO_V6_COMPLETION_NAME = "executive-schema-upgrade.v5-to-v6.completion.json"
_UPGRADE_V6_TO_V7_PREFLIGHT_NAME = "executive-schema-upgrade.v6-to-v7.preflight.json"
_UPGRADE_V6_TO_V7_COMPLETION_NAME = "executive-schema-upgrade.v6-to-v7.completion.json"
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class ExecutiveBackupError(RuntimeProofError):
    """Base class for operator-visible Executive backup failures."""


class BackupVerificationError(ExecutiveBackupError):
    """A backup, manifest, or restored database failed closed verification."""


class RestoreSafetyError(ExecutiveBackupError):
    """An offline restore could not prove that the service was stopped."""


class RestoreRollbackError(ExecutiveBackupError):
    """A restore failed after replacement and the prior bytes were restored."""


class ExecutiveSchemaUpgradeError(RuntimeProofError):
    """The explicit offline schema upgrade failed closed."""


@dataclasses.dataclass(frozen=True)
class SchemaUpgradeReceipt:
    schema_version: str
    database_path: str
    release_sha: str
    preflight_receipt_path: str
    preflight_receipt_digest: str
    completion_receipt_path: str
    completion_receipt_digest: str
    pre_v4_legacy_content_digest: str
    post_v4_legacy_content_digest: str
    v3_backup_path: str
    v4_backup_path: str
    completed_at: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class SchemaUpgradeV4ToV5Receipt:
    """Durable receipt for the explicit offline exact-v4 -> v5 transition.

    The v3/v4-named fields of ``SchemaUpgradeReceipt`` keep their historical
    meaning for the prior transition; this separate additive receipt names its
    own source (4) and target (5) and proves full-v4 content equality.
    """

    schema_version: str
    database_path: str
    database_identity: dict[str, Any]
    release_sha: str
    preflight_receipt_path: str
    preflight_receipt_digest: str
    completion_receipt_path: str
    completion_receipt_digest: str
    source_schema_version: int
    target_schema_version: int
    pre_full_v4_content_digest: str
    post_full_v4_content_digest: str
    full_v4_content_equal: bool
    v4_backup_path: str
    v4_backup_manifest_path: str
    v5_backup_path: str
    v5_backup_manifest_path: str
    completed_at: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class SchemaUpgradeV5ToV6Receipt:
    """Evidence for the exact-v5 -> v6 upgrade, including retained v5 history."""

    schema_version: str
    database_path: str
    database_identity: dict[str, Any]
    release_sha: str
    preflight_receipt_path: str
    preflight_receipt_digest: str
    completion_receipt_path: str
    completion_receipt_digest: str
    source_schema_version: int
    target_schema_version: int
    pre_full_v4_content_digest: str
    post_full_v4_content_digest: str
    pre_v5_migration_receipt_digest: str
    post_v5_migration_receipt_digest: str
    full_v4_content_equal: bool
    v5_backup_path: str
    v5_backup_manifest_path: str
    v6_backup_path: str
    v6_backup_manifest_path: str
    completed_at: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class SchemaUpgradeV6ToV7Receipt:
    """Receipt for the closed offline exact-v6 to v7 transition.

    It binds preserved full-v6 content, the exact physical-history postimage,
    and both source and target backup/drill proofs under the incumbent owner.
    """

    schema_version: str
    database_path: str
    database_identity: dict[str, Any]
    release_sha: str
    preflight_receipt_path: str
    preflight_receipt_digest: str
    completion_receipt_path: str
    completion_receipt_digest: str
    source_schema_version: int
    target_schema_version: int
    pre_full_v6_content_digest: str
    post_full_v6_content_digest: str
    full_v6_content_equal: bool
    physical_history_digest: str
    v6_backup_path: str
    v6_backup_manifest_path: str
    v7_backup_path: str
    v7_backup_manifest_path: str
    completed_at: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


# Test seams are module-private and carry no authority through the public API.
# Production always uses the installed-release and operating-system observers.
_SCHEMA_UPGRADE_TEST_HOOK: Callable[[str], None] | None = None
_SCHEMA_UPGRADE_RELEASE_OBSERVER: Callable[[], Mapping[str, str]] | None = None
_SCHEMA_UPGRADE_CENSUS_OBSERVER: (
    Callable[[Path, Path, Path, int], Mapping[str, Any]] | None
) = None


@dataclasses.dataclass(frozen=True)
class MigrationReceipt:
    version: int
    name: str
    checksum: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class BackupVerification:
    database_path: str
    database_sha256: str
    database_size: int
    page_count: int
    page_size: int
    migrations: tuple[MigrationReceipt, ...]
    normalized_schema_digest: str
    legacy_content_digest: str
    manifest_path: str | None = None
    manifest_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "database_path": self.database_path,
            "database_sha256": self.database_sha256,
            "database_size": self.database_size,
            "page_count": self.page_count,
            "page_size": self.page_size,
            "migrations": [item.to_dict() for item in self.migrations],
            "normalized_schema_digest": self.normalized_schema_digest,
            "legacy_content_digest": self.legacy_content_digest,
            "manifest_path": self.manifest_path,
            "manifest_sha256": self.manifest_sha256,
        }


@dataclasses.dataclass(frozen=True)
class BackupReceipt:
    backup_id: str
    created_at: str
    database_path: str
    database_sha256: str
    database_size: int
    manifest_path: str
    manifest_sha256: str
    migrations: tuple[MigrationReceipt, ...]
    normalized_schema_digest: str
    legacy_content_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "backup_id": self.backup_id,
            "created_at": self.created_at,
            "database_path": self.database_path,
            "database_sha256": self.database_sha256,
            "database_size": self.database_size,
            "manifest_path": self.manifest_path,
            "manifest_sha256": self.manifest_sha256,
            "migrations": [item.to_dict() for item in self.migrations],
            "normalized_schema_digest": self.normalized_schema_digest,
            "legacy_content_digest": self.legacy_content_digest,
        }


@dataclasses.dataclass(frozen=True)
class RestoreDrillReceipt:
    database_sha256: str
    runtime_schema_version: int
    migration_versions: tuple[int, ...]
    integrity_check: str = "ok"
    foreign_key_check: str = "ok"
    normalized_schema_digest: str = ""
    legacy_content_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class RestoreReceipt:
    restored_database_path: str
    restored_sha256: str
    rollback_database_path: str
    rollback_sidecar_paths: tuple[str, ...]
    rollback_sha256: str
    manifest_sha256: str
    restored_at: str
    source_backup_sha256: str | None = None
    final_runtime_sha256: str | None = None
    ohf_invalidated_attempts: int = 0
    physical_history_digest: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise BackupVerificationError(f"cannot hash backup file: {exc}") from exc
    return digest.hexdigest()


def _ensure_private_directory(path: Path) -> Path:
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = path.lstat()
    except OSError as exc:
        raise ExecutiveBackupError(
            f"cannot prepare private backup directory: {exc}"
        ) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ExecutiveBackupError(f"backup path is not a real directory: {path}")
    if info.st_uid != os.geteuid():
        raise ExecutiveBackupError(
            f"backup directory is not owned by the control principal: {path}"
        )
    try:
        path.chmod(0o700)
    except OSError as exc:
        raise ExecutiveBackupError(f"cannot protect backup directory: {exc}") from exc
    return path.resolve(strict=True)


def _assert_private_regular_file(path: Path, *, label: str) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as exc:
        raise BackupVerificationError(f"{label} is unavailable: {exc}") from exc
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
    ):
        raise BackupVerificationError(f"{label} must be a single-link regular file")
    if info.st_uid != os.geteuid():
        raise BackupVerificationError(f"{label} is not owned by the control principal")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise BackupVerificationError(f"{label} is accessible to group or other")
    return info


def _fsync_path(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_private_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:  # pragma: no cover - defensive OS boundary
                raise OSError("short write while persisting backup manifest")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def _copy_private_file(source: Path, destination: Path) -> None:
    _assert_private_regular_file(source, label="source database")
    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        with (
            source.open("rb") as input_handle,
            os.fdopen(descriptor, "wb", closefd=False) as output,
        ):
            shutil.copyfileobj(input_handle, output, length=1024 * 1024)
            output.flush()
            os.fsync(descriptor)
    except Exception:
        try:
            destination.unlink()
        except OSError:
            pass
        raise
    finally:
        os.close(descriptor)


def _closed_schema_version(value: int) -> int:
    if type(value) is not int or value not in {3, 4, 5, 6, 7}:
        raise BackupVerificationError(
            "expected schema version must be exactly 3, 4, 5, 6, or 7"
        )
    return value


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise BackupVerificationError(f"canonical Executive evidence failed: {exc}") from exc


def _normalize_sql_outside_literals(sql: str) -> str:
    result: list[str] = []
    quote_char: str | None = None
    bracket = False
    pending_space = False
    index = 0
    while index < len(sql):
        character = sql[index]
        if quote_char is not None:
            result.append(character)
            if character == quote_char:
                if index + 1 < len(sql) and sql[index + 1] == quote_char:
                    result.append(sql[index + 1])
                    index += 1
                else:
                    quote_char = None
            index += 1
            continue
        if bracket:
            result.append(character)
            if character == "]":
                bracket = False
            index += 1
            continue
        if character in {"'", '"', "`"}:
            if pending_space and result:
                result.append(" ")
            pending_space = False
            quote_char = character
            result.append(character)
        elif character == "[":
            if pending_space and result:
                result.append(" ")
            pending_space = False
            bracket = True
            result.append(character)
        elif character.isspace():
            pending_space = True
        else:
            if pending_space and result:
                result.append(" ")
            pending_space = False
            result.append(character)
        index += 1
    if quote_char is not None or bracket:
        raise BackupVerificationError("sqlite_schema contains unterminated quoted SQL")
    return "".join(result).strip()


def _normalized_schema(connection: sqlite3.Connection) -> list[list[str]]:
    rows = connection.execute(
        """
        SELECT type,name,tbl_name,sql FROM sqlite_master
        WHERE sql IS NOT NULL
        ORDER BY type COLLATE BINARY,name COLLATE BINARY
        """
    ).fetchall()
    return [
        [
            str(row[0]),
            str(row[1]),
            str(row[2]),
            _normalize_sql_outside_literals(str(row[3])),
        ]
        for row in rows
    ]


def normalized_schema_digest(connection: sqlite3.Connection) -> str:
    return hashlib.sha256(_canonical_bytes(_normalized_schema(connection))).hexdigest()


def _reference_normalized_schema_digest_for_tests(expected_schema_version: int) -> str:
    """Construct the reviewed reference only in tests/maintenance, never verify."""
    expected_schema_version = _closed_schema_version(expected_schema_version)
    connection = sqlite3.connect(":memory:", isolation_level=None)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            """
            CREATE TABLE schema_migrations (
              version INTEGER PRIMARY KEY,
              name TEXT NOT NULL UNIQUE,
              checksum TEXT NOT NULL,
              applied_at_ms INTEGER NOT NULL
            )
            """
        )
        for version, _name, statements in _MIGRATIONS:
            if version > expected_schema_version:
                break
            for statement in statements:
                connection.execute(statement)
        return normalized_schema_digest(connection)
    finally:
        connection.close()


def _tagged_cell(storage_class: str, value: Any) -> list[str]:
    if storage_class == "null" and value is None:
        return ["null"]
    if storage_class == "integer" and type(value) is int:
        return ["integer", str(value)]
    if storage_class == "text" and isinstance(value, str):
        value.encode("utf-8", errors="strict")
        return ["text", value]
    raise BackupVerificationError(
        f"legacy content contains unsupported SQLite storage class {storage_class!r}"
    )


def legacy_content_projection(
    connection: sqlite3.Connection,
    *,
    expected_schema_version: int,
) -> dict[str, Any]:
    """Return the closed v1-v3 logical projection from exact v3, v4, or v5.

    A v5 store carries the identical historical material, so it projects the
    same v1-v3 content the v3 and v4 stores do.
    """

    expected_schema_version = _closed_schema_version(expected_schema_version)
    tables: list[dict[str, Any]] = []
    for name, columns, primary_key in _LEGACY_TABLE_COLUMNS:
        actual_columns = tuple(
            str(row[1]) for row in connection.execute(f'PRAGMA table_info("{name}")')
        )
        expected_columns = columns
        if expected_schema_version >= 4 and name == "jobs":
            expected_columns = (*columns, *_V4_JOB_COLUMNS)
        elif expected_schema_version >= 4 and name == "attempts":
            expected_columns = (*columns, *_V4_ATTEMPT_COLUMNS)
        if actual_columns != expected_columns:
            raise BackupVerificationError(
                f"{name} columns do not match exact schema v{expected_schema_version}"
            )
        select_parts: list[str] = []
        for column in columns:
            select_parts.extend((f'typeof("{column}")', f'"{column}"'))
        order = ",".join(f'"{column}" COLLATE BINARY' for column in primary_key)
        raw_rows = connection.execute(
            f'SELECT {",".join(select_parts)} FROM "{name}" ORDER BY {order}'
        ).fetchall()
        projected_rows: list[list[list[str]]] = []
        seen_keys: set[tuple[tuple[str, ...], ...]] = set()
        key_indexes = [columns.index(column) for column in primary_key]
        for raw in raw_rows:
            tagged = [
                _tagged_cell(str(raw[index * 2]), raw[index * 2 + 1])
                for index in range(len(columns))
            ]
            key = tuple(tuple(tagged[index]) for index in key_indexes)
            if key in seen_keys:
                raise BackupVerificationError(f"{name} has a duplicate logical key")
            seen_keys.add(key)
            projected_rows.append(tagged)
        tables.append(
            {
                "name": name,
                "columns": list(columns),
                "primary_key": list(primary_key),
                "rows": projected_rows,
            }
        )
    migration_rows = connection.execute(
        """
        SELECT typeof(version),version,typeof(name),name,typeof(checksum),checksum,
               typeof(applied_at_ms),applied_at_ms
        FROM schema_migrations WHERE version<=3 ORDER BY version
        """
    ).fetchall()
    if len(migration_rows) != 3:
        raise BackupVerificationError("legacy migration vector must contain exact v1-v3 rows")
    expected_receipts = _expected_migrations(3)
    for ordinal, (row, expected) in enumerate(zip(migration_rows, expected_receipts), 1):
        if (
            row[0] != "integer"
            or type(row[1]) is not int
            or row[1] != ordinal
            or row[2] != "text"
            or row[3] != expected.name
            or row[4] != "text"
            or row[5] != expected.checksum
            or row[6] != "integer"
            or type(row[7]) is not int
        ):
            raise BackupVerificationError(
                "legacy migration vector identity/storage class is invalid"
            )
    migration_vector = [
        [
            _tagged_cell(str(row[0]), row[1]),
            _tagged_cell(str(row[2]), row[3]),
            _tagged_cell(str(row[4]), row[5]),
            _tagged_cell(str(row[6]), row[7]),
        ]
        for row in migration_rows
    ]
    return {
        "schema_version": LEGACY_CONTENT_PROJECTION_SCHEMA,
        "source_schema_version": 3,
        "tables": tables,
        "legacy_migration_vector": migration_vector,
    }


def legacy_content_digest(
    connection: sqlite3.Connection,
    *,
    expected_schema_version: int,
) -> str:
    return hashlib.sha256(
        _canonical_bytes(
            legacy_content_projection(
                connection, expected_schema_version=expected_schema_version
            )
        )
    ).hexdigest()


def full_v4_content_projection(connection: sqlite3.Connection) -> dict[str, Any]:
    """Return the closed full-v4 content projection from an exact v4 store.

    Covers all eight retained tables with every v4 column (including the
    v4-only orchestration, grant, placement, and principal fields), plus the
    schema_migrations rows 1-4 with their exact original ``applied_at_ms``
    timestamps.  The migration-5 receipt row is deliberately outside this
    projection, so the same digest also proves v4 content preservation when
    read from a migrated v5 store.
    """

    tables: list[dict[str, Any]] = []
    for name, columns, primary_key in _FULL_V4_TABLE_COLUMNS:
        actual_columns = tuple(
            str(row[1]) for row in connection.execute(f'PRAGMA table_info("{name}")')
        )
        if actual_columns != columns:
            raise BackupVerificationError(f"{name} columns do not match exact schema v4")
        select_parts: list[str] = []
        for column in columns:
            select_parts.extend((f'typeof("{column}")', f'"{column}"'))
        order = ",".join(f'"{column}" COLLATE BINARY' for column in primary_key)
        raw_rows = connection.execute(
            f'SELECT {",".join(select_parts)} FROM "{name}" ORDER BY {order}'
        ).fetchall()
        projected_rows: list[list[list[str]]] = []
        seen_keys: set[tuple[tuple[str, ...], ...]] = set()
        key_indexes = [columns.index(column) for column in primary_key]
        for raw in raw_rows:
            tagged = [
                _tagged_cell(str(raw[index * 2]), raw[index * 2 + 1])
                for index in range(len(columns))
            ]
            key = tuple(tuple(tagged[index]) for index in key_indexes)
            if key in seen_keys:
                raise BackupVerificationError(f"{name} has a duplicate logical key")
            seen_keys.add(key)
            projected_rows.append(tagged)
        tables.append(
            {
                "name": name,
                "columns": list(columns),
                "primary_key": list(primary_key),
                "rows": projected_rows,
            }
        )
    migration_rows = connection.execute(
        """
        SELECT typeof(version),version,typeof(name),name,typeof(checksum),checksum,
               typeof(applied_at_ms),applied_at_ms
        FROM schema_migrations WHERE version<=4 ORDER BY version
        """
    ).fetchall()
    if len(migration_rows) != 4:
        raise BackupVerificationError("full v4 migration vector must contain exact v1-v4 rows")
    expected_receipts = _expected_migrations(4)
    for ordinal, (row, expected) in enumerate(zip(migration_rows, expected_receipts), 1):
        if (
            row[0] != "integer"
            or type(row[1]) is not int
            or row[1] != ordinal
            or row[2] != "text"
            or row[3] != expected.name
            or row[4] != "text"
            or row[5] != expected.checksum
            or row[6] != "integer"
            or type(row[7]) is not int
        ):
            raise BackupVerificationError(
                "full v4 migration vector identity/storage class is invalid"
            )
    migration_vector = [
        [
            _tagged_cell(str(row[0]), row[1]),
            _tagged_cell(str(row[2]), row[3]),
            _tagged_cell(str(row[4]), row[5]),
            _tagged_cell(str(row[6]), row[7]),
        ]
        for row in migration_rows
    ]
    return {
        "schema_version": FULL_V4_CONTENT_PROJECTION_SCHEMA,
        "source_schema_version": 4,
        "tables": tables,
        "v4_migration_vector": migration_vector,
    }


def full_v4_content_digest(connection: sqlite3.Connection) -> str:
    return hashlib.sha256(
        _canonical_bytes(full_v4_content_projection(connection))
    ).hexdigest()



def full_v5_content_projection(connection: sqlite3.Connection) -> dict[str, Any]:
    """Preserve every v5 cell and all five original migration timestamps.

    Migrations 6 and 7 and the new physical tables are outside this projection.
    The existing full-v4 projection already covers every retained table column.
    """
    prior = full_v4_content_projection(connection)
    rows = connection.execute(
        "SELECT typeof(version),version,typeof(name),name,typeof(checksum),checksum,"
        "typeof(applied_at_ms),applied_at_ms FROM schema_migrations WHERE version=5"
    ).fetchall()
    expected = _expected_migrations(5)[4]
    if len(rows) != 1:
        raise BackupVerificationError("full v5 projection requires migration 5")
    row = rows[0]
    if (
        row[0] != "integer" or type(row[1]) is not int or row[1] != 5
        or row[2] != "text" or row[3] != expected.name
        or row[4] != "text" or row[5] != expected.checksum
        or row[6] != "integer" or type(row[7]) is not int
    ):
        raise BackupVerificationError("full v5 migration identity/storage class is invalid")
    last = [_tagged_cell(str(row[index]), row[index + 1]) for index in (0, 2, 4, 6)]
    return {
        "schema_version": FULL_V5_CONTENT_PROJECTION_SCHEMA,
        "source_schema_version": 5,
        "tables": prior["tables"],
        "v5_migration_vector": [*prior["v4_migration_vector"], last],
    }


def full_v5_content_digest(connection: sqlite3.Connection) -> str:
    return hashlib.sha256(_canonical_bytes(full_v5_content_projection(connection))).hexdigest()


def full_v6_content_projection(connection: sqlite3.Connection) -> dict[str, Any]:
    """Preserve every v6 cell and all six original migration timestamps.

    Migration 7 and its two new physical tables are outside this projection.
    The existing full-v4 projection already covers every retained table column.
    """
    prior = full_v5_content_projection(connection)
    rows = connection.execute(
        "SELECT typeof(version),version,typeof(name),name,typeof(checksum),checksum,"
        "typeof(applied_at_ms),applied_at_ms FROM schema_migrations WHERE version=6"
    ).fetchall()
    expected = _expected_migrations(6)[5]
    if len(rows) != 1:
        raise BackupVerificationError("full v6 projection requires migration 6")
    row = rows[0]
    if (
        row[0] != "integer" or type(row[1]) is not int or row[1] != 6
        or row[2] != "text" or row[3] != expected.name
        or row[4] != "text" or row[5] != expected.checksum
        or row[6] != "integer" or type(row[7]) is not int
    ):
        raise BackupVerificationError("full v6 migration identity/storage class is invalid")
    last = [_tagged_cell(str(row[index]), row[index + 1]) for index in (0, 2, 4, 6)]
    return {
        "schema_version": FULL_V6_CONTENT_PROJECTION_SCHEMA,
        "source_schema_version": 6,
        "tables": prior["tables"],
        "v6_migration_vector": [*prior["v5_migration_vector"], last],
    }


def full_v6_content_digest(connection: sqlite3.Connection) -> str:
    return hashlib.sha256(_canonical_bytes(full_v6_content_projection(connection))).hexdigest()


def physical_history_projection(connection: sqlite3.Connection) -> dict[str, Any]:
    """Return exact physical rows and Events, not an aggregate charge total.

    Includes every commitment state, terminal tombstone, demand attribution,
    refusal/replay Event, storage class, identity, revision and causal Event ID.
    The caller separately verifies the complete schema and database custody.
    """
    tables: list[dict[str, Any]] = []
    for name, columns, primary_key in _PHYSICAL_HISTORY_TABLE_COLUMNS:
        actual = tuple(str(row[1]) for row in connection.execute(f'PRAGMA table_info("{name}")'))
        if actual != columns:
            raise BackupVerificationError(f"{name} columns differ from physical history schema")
        select_parts = [
            part for column in columns
            for part in (f'typeof("{column}")', f'"{column}"')
        ]
        order = ",".join(f'"{column}" COLLATE BINARY' for column in primary_key)
        where = f" WHERE {_PHYSICAL_EVENT_PREDICATE}" if name == "events" else ""
        raw_rows = connection.execute(
            f'SELECT {",".join(select_parts)} FROM "{name}"{where} ORDER BY {order}'
        ).fetchall()
        rows = [
            [_tagged_cell(str(row[index * 2]), row[index * 2 + 1]) for index in range(len(columns))]
            for row in raw_rows
        ]
        keys = [
            tuple(tuple(row[columns.index(key)]) for key in primary_key)
            for row in rows
        ]
        if len(set(keys)) != len(keys):
            raise BackupVerificationError(f"{name} has duplicate physical history identity")
        tables.append({"name": name, "columns": list(columns),
                       "primary_key": list(primary_key), "rows": rows})
    return {"schema_version": PHYSICAL_HISTORY_PROJECTION_SCHEMA, "tables": tables}


def physical_history_digest(connection: sqlite3.Connection) -> str:
    return hashlib.sha256(_canonical_bytes(physical_history_projection(connection))).hexdigest()


def _require_no_physical_events(connection: sqlite3.Connection) -> None:
    if connection.execute(f"SELECT 1 FROM events WHERE {_PHYSICAL_EVENT_PREDICATE} LIMIT 1").fetchone():
        raise ExecutiveSchemaUpgradeError("initial physical migration refuses preexisting physical Events")


def _require_initial_physical_history(connection: sqlite3.Connection) -> str:
    _require_no_physical_events(connection)
    for name, _columns, _key in _PHYSICAL_HISTORY_TABLE_COLUMNS[:2]:
        if connection.execute(f'SELECT 1 FROM "{name}" LIMIT 1').fetchone():
            raise ExecutiveSchemaUpgradeError("initial physical migration requires empty physical tables")
    return physical_history_digest(connection)


def _expected_migrations(
    expected_schema_version: int = SCHEMA_VERSION,
) -> tuple[MigrationReceipt, ...]:
    expected_schema_version = _closed_schema_version(expected_schema_version)
    return tuple(
        MigrationReceipt(
            version=int(version),
            name=str(name),
            checksum=hashlib.sha256(
                "\n".join(statement.strip() for statement in statements).encode("utf-8")
            ).hexdigest(),
        )
        for version, name, statements in _MIGRATIONS
        if version <= expected_schema_version
    )


def _verify_connection(
    connection: sqlite3.Connection,
    *,
    expected_schema_version: int = SCHEMA_VERSION,
) -> tuple[int, int, tuple[MigrationReceipt, ...]]:
    expected_schema_version = _closed_schema_version(expected_schema_version)
    try:
        integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
        if [str(row[0]) for row in integrity_rows] != ["ok"]:
            raise BackupVerificationError("SQLite integrity_check did not return ok")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise BackupVerificationError("SQLite foreign_key_check found violations")
        rows = connection.execute(
            "SELECT version,name,checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
        actual = tuple(
            MigrationReceipt(
                version=int(row[0]),
                name=str(row[1]),
                checksum=str(row[2]),
            )
            for row in rows
        )
        expected = _expected_migrations(expected_schema_version)
        if actual != expected:
            raise BackupVerificationError(
                "database migrations do not exactly match the migrations known to this runtime"
            )
        actual_schema_digest = normalized_schema_digest(connection)
        expected_schema_digest = _NORMALIZED_SCHEMA_DIGESTS[expected_schema_version]
        if actual_schema_digest != expected_schema_digest:
            raise BackupVerificationError(
                f"database normalized schema does not match exact v{expected_schema_version}"
            )
        legacy_content_projection(
            connection, expected_schema_version=expected_schema_version
        )
        if expected_schema_version == 3:
            leaked = connection.execute(
                """
                SELECT event_id FROM events
                WHERE event_type IN (
                  'COO_PLAN_ADMITTED','COO_AGGREGATION_HANDOFF_READY',
                  'COO_CYCLE_BLOCKED',
                  'ORCHESTRATION_WORK_ADMITTED','ORCHESTRATION_ROLE_RESULT_SEALED'
                )
                LIMIT 1
                """
            ).fetchone()
            if leaked is not None:
                raise BackupVerificationError(
                    "exact v3 database contains a Phase 1F-C Event"
                )
            semantic_rows = connection.execute(
                """
                SELECT event_type,command_id,payload_json FROM events
                WHERE event_type IN ('JOB_CREATED','JOB_CLAIMED','JOB_REQUEUED')
                   OR command_id LIKE 'coo-cycle:%'
                ORDER BY event_id
                """
            ).fetchall()
            for semantic_row in semantic_rows:
                payload = _strict_json(str(semantic_row[2]).encode("utf-8"))
                if not isinstance(payload, dict):
                    raise BackupVerificationError("legacy Event payload is not an object")
                event_type = str(semantic_row[0])
                command_id = str(semantic_row[1])
                v4_payload_keys = {
                    "orchestration_role",
                    "orchestration_provenance_digest",
                    "plan_attempt_id",
                    "plan_digest",
                    "plan_step_id",
                    "repair_round",
                    "supersedes_job_id",
                    "effective_grant_digest",
                    "placement_snapshot_digest",
                    "cycle_command_id",
                    "dispatch_job_id",
                    "requeue_kind",
                    "invalidated_quota_snapshot",
                    "tx9_evidence_digest",
                }
                if command_id.startswith("coo-cycle:") or set(payload) & v4_payload_keys:
                    raise BackupVerificationError(
                        f"exact v3 database contains v4 semantics in {event_type}"
                    )
        page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        if page_count <= 0 or page_size <= 0:
            raise BackupVerificationError("SQLite page metadata is invalid")
        return page_count, page_size, actual
    except BackupVerificationError:
        raise
    except sqlite3.Error as exc:
        raise BackupVerificationError(f"SQLite verification failed: {exc}") from exc


@contextmanager
def _readonly_database(path: Path) -> Iterator[sqlite3.Connection]:
    encoded = quote(str(path), safe="/")
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(
            f"file:{encoded}?mode=ro&immutable=1",
            uri=True,
            isolation_level=None,
            timeout=5.0,
        )
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        yield connection
    except BackupVerificationError:
        raise
    except sqlite3.Error as exc:
        raise BackupVerificationError(f"cannot open backup read-only: {exc}") from exc
    finally:
        if connection is not None:
            connection.close()


def _verify_database_file(
    path: Path, *, expected_schema_version: int = SCHEMA_VERSION
) -> BackupVerification:
    candidate = path.expanduser()
    _assert_private_regular_file(candidate, label="backup database")
    resolved = candidate.resolve(strict=True)
    info = _assert_private_regular_file(resolved, label="backup database")
    if info.st_size <= 0:
        raise BackupVerificationError("backup database is empty")
    database_hash = _sha256_path(resolved)
    with _readonly_database(resolved) as connection:
        page_count, page_size, migrations = _verify_connection(
            connection, expected_schema_version=expected_schema_version
        )
        schema_digest = normalized_schema_digest(connection)
        content_digest = legacy_content_digest(
            connection, expected_schema_version=expected_schema_version
        )
    return BackupVerification(
        database_path=str(resolved),
        database_sha256=database_hash,
        database_size=info.st_size,
        page_count=page_count,
        page_size=page_size,
        migrations=migrations,
        normalized_schema_digest=schema_digest,
        legacy_content_digest=content_digest,
    )


def _strict_json(raw: bytes) -> Any:
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise BackupVerificationError(
                    f"backup manifest has duplicate key {key!r}"
                )
            result[key] = value
        return result

    try:
        return json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=pairs)
    except BackupVerificationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackupVerificationError(
            f"backup manifest is not strict UTF-8 JSON: {exc}"
        ) from exc


def _load_manifest(path: Path) -> tuple[dict[str, Any], str]:
    candidate = path.expanduser()
    _assert_private_regular_file(candidate, label="backup manifest")
    resolved = candidate.resolve(strict=True)
    info = _assert_private_regular_file(resolved, label="backup manifest")
    if info.st_size <= 0 or info.st_size > _MAX_MANIFEST_BYTES:
        raise BackupVerificationError("backup manifest is empty or exceeds 64 KiB")
    raw = resolved.read_bytes()
    value = _strict_json(raw)
    if not isinstance(value, dict):
        raise BackupVerificationError("backup manifest root must be an object")
    return value, hashlib.sha256(raw).hexdigest()


def _manifest_payload(
    *,
    backup_id: str,
    created_at: str,
    database_name: str,
    verification: BackupVerification,
    runtime_schema_version: int = SCHEMA_VERSION,
) -> dict[str, Any]:
    return {
        "schema_version": BACKUP_MANIFEST_SCHEMA_VERSION,
        "backup_id": backup_id,
        "created_at": created_at,
        "runtime_schema_version": _closed_schema_version(runtime_schema_version),
        "database": {
            "filename": database_name,
            "sha256": verification.database_sha256,
            "size_bytes": verification.database_size,
        },
        "sqlite": {
            "integrity_check": "ok",
            "foreign_key_check": "ok",
            "page_count": verification.page_count,
            "page_size": verification.page_size,
        },
        "migrations": [item.to_dict() for item in verification.migrations],
    }


def _verify_manifest(
    manifest: Mapping[str, Any],
    *,
    database_path: Path,
    verification: BackupVerification,
    expected_schema_version: int = SCHEMA_VERSION,
) -> None:
    expected_schema_version = _closed_schema_version(expected_schema_version)
    expected_top = {
        "schema_version",
        "backup_id",
        "created_at",
        "runtime_schema_version",
        "database",
        "sqlite",
        "migrations",
    }
    if set(manifest) != expected_top:
        raise BackupVerificationError(
            "backup manifest has an unknown or missing top-level field"
        )
    if manifest.get("schema_version") != BACKUP_MANIFEST_SCHEMA_VERSION:
        raise BackupVerificationError("backup manifest schema version is unsupported")
    if not isinstance(manifest.get("backup_id"), str) or not _BACKUP_ID_RE.fullmatch(
        str(manifest["backup_id"])
    ):
        raise BackupVerificationError("backup manifest ID is invalid")
    if not isinstance(manifest.get("created_at"), str) or not manifest["created_at"]:
        raise BackupVerificationError("backup manifest creation time is invalid")
    if manifest.get("runtime_schema_version") != expected_schema_version:
        raise BackupVerificationError(
            "backup manifest runtime schema version differs from code"
        )

    database = manifest.get("database")
    if not isinstance(database, dict) or set(database) != {
        "filename",
        "sha256",
        "size_bytes",
    }:
        raise BackupVerificationError("backup manifest database receipt is invalid")
    if database.get("filename") != database_path.name:
        raise BackupVerificationError(
            "backup manifest filename does not match the database"
        )
    if not isinstance(database.get("sha256"), str) or not _HASH_RE.fullmatch(
        database["sha256"]
    ):
        raise BackupVerificationError("backup manifest database hash is invalid")
    if database["sha256"] != verification.database_sha256:
        raise BackupVerificationError(
            "backup database hash does not match its manifest"
        )
    if database.get("size_bytes") != verification.database_size:
        raise BackupVerificationError(
            "backup database size does not match its manifest"
        )

    sqlite_receipt = manifest.get("sqlite")
    if not isinstance(sqlite_receipt, dict) or set(sqlite_receipt) != {
        "integrity_check",
        "foreign_key_check",
        "page_count",
        "page_size",
    }:
        raise BackupVerificationError("backup manifest SQLite receipt is invalid")
    if (
        sqlite_receipt.get("integrity_check") != "ok"
        or sqlite_receipt.get("foreign_key_check") != "ok"
    ):
        raise BackupVerificationError(
            "backup manifest does not attest healthy SQLite checks"
        )
    if (
        sqlite_receipt.get("page_count") != verification.page_count
        or sqlite_receipt.get("page_size") != verification.page_size
    ):
        raise BackupVerificationError(
            "backup SQLite page metadata does not match its manifest"
        )

    migrations = manifest.get("migrations")
    expected_migrations = [item.to_dict() for item in verification.migrations]
    if migrations != expected_migrations:
        raise BackupVerificationError(
            "backup migration receipt does not match the database"
        )


def create_online_backup(
    store: RuntimeStore, destination_directory: str | Path
) -> BackupReceipt:
    """Create and verify one owner-only online SQLite backup plus safe manifest."""

    destination = _ensure_private_directory(Path(destination_directory).expanduser())
    backup_id = uuid4().hex
    created_at = _utc_now()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    database_path = destination / f"executive-{stamp}-{backup_id}.sqlite3"
    manifest_path = database_path.with_suffix(".manifest.json")
    temporary_path = destination / f".{database_path.name}.tmp"
    descriptor = os.open(
        temporary_path,
        os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    os.close(descriptor)
    destination_connection: sqlite3.Connection | None = None
    try:
        destination_connection = sqlite3.connect(
            temporary_path,
            isolation_level=None,
            timeout=max(5.0, store.busy_timeout_ms / 1000),
        )
        with store.read() as source_connection:
            source_connection.backup(destination_connection)
        destination_connection.close()
        destination_connection = None
        temporary_path.chmod(0o600)
        _fsync_path(temporary_path)
        verification = _verify_database_file(temporary_path)
        os.replace(temporary_path, database_path)
        _fsync_directory(destination)
        verification = dataclasses.replace(
            verification,
            database_path=str(database_path),
        )
        manifest = _manifest_payload(
            backup_id=backup_id,
            created_at=created_at,
            database_name=database_path.name,
            verification=verification,
        )
        _write_private_json(manifest_path, manifest)
        checked = verify_backup(database_path, manifest_path)
        assert checked.manifest_sha256 is not None
        return BackupReceipt(
            backup_id=backup_id,
            created_at=created_at,
            database_path=str(database_path),
            database_sha256=checked.database_sha256,
            database_size=checked.database_size,
            manifest_path=str(manifest_path),
            manifest_sha256=checked.manifest_sha256,
            migrations=checked.migrations,
            normalized_schema_digest=checked.normalized_schema_digest,
            legacy_content_digest=checked.legacy_content_digest,
        )
    except Exception:
        for path in (temporary_path, manifest_path, database_path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        if destination_connection is not None:
            destination_connection.close()


def create_offline_backup(
    database_path: str | Path,
    destination_directory: str | Path,
    *,
    expected_schema_version: int,
) -> BackupReceipt:
    """Copy one quiesced exact-v3/v4/v5 database without constructing RuntimeStore."""

    expected_schema_version = _closed_schema_version(expected_schema_version)
    source_candidate = Path(database_path).expanduser()
    if any(os.path.lexists(_sidecar(source_candidate, suffix)) for suffix in _SIDECAR_SUFFIXES):
        raise BackupVerificationError(
            "offline backup source has SQLite sidecars; checkpoint/quiesce first"
        )
    source_verification = verify_backup(
        source_candidate, expected_schema_version=expected_schema_version
    )
    destination = _ensure_private_directory(Path(destination_directory).expanduser())
    backup_id = uuid4().hex
    created_at = _utc_now()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    final_path = destination / f"executive-v{expected_schema_version}-{stamp}-{backup_id}.sqlite3"
    temporary = destination / f".{final_path.name}.tmp"
    manifest_path = final_path.with_suffix(".manifest.json")
    descriptor = os.open(
        temporary,
        os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    os.close(descriptor)
    source_connection: sqlite3.Connection | None = None
    destination_connection: sqlite3.Connection | None = None
    try:
        source_connection = sqlite3.connect(
            f"{Path(source_verification.database_path).as_uri()}?mode=ro&immutable=1",
            uri=True,
            isolation_level=None,
            timeout=5.0,
        )
        source_connection.execute("PRAGMA query_only=ON")
        destination_connection = sqlite3.connect(temporary, isolation_level=None)
        source_connection.backup(destination_connection)
        destination_connection.close()
        destination_connection = None
        source_connection.close()
        source_connection = None
        temporary.chmod(0o600)
        _fsync_path(temporary)
        copied = _verify_database_file(
            temporary, expected_schema_version=expected_schema_version
        )
        if (
            copied.normalized_schema_digest
            != source_verification.normalized_schema_digest
            or copied.legacy_content_digest
            != source_verification.legacy_content_digest
        ):
            raise BackupVerificationError(
                "offline backup copy changed normalized schema or legacy content"
            )
        os.replace(temporary, final_path)
        _fsync_directory(destination)
        copied = dataclasses.replace(copied, database_path=str(final_path))
        manifest = _manifest_payload(
            backup_id=backup_id,
            created_at=created_at,
            database_name=final_path.name,
            verification=copied,
            runtime_schema_version=expected_schema_version,
        )
        _write_private_json(manifest_path, manifest)
        checked = verify_backup(
            final_path,
            manifest_path,
            expected_schema_version=expected_schema_version,
        )
        assert checked.manifest_sha256 is not None
        return BackupReceipt(
            backup_id=backup_id,
            created_at=created_at,
            database_path=str(final_path),
            database_sha256=checked.database_sha256,
            database_size=checked.database_size,
            manifest_path=str(manifest_path),
            manifest_sha256=checked.manifest_sha256,
            migrations=checked.migrations,
            normalized_schema_digest=checked.normalized_schema_digest,
            legacy_content_digest=checked.legacy_content_digest,
        )
    except Exception:
        for path in (temporary, final_path, manifest_path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        if source_connection is not None:
            source_connection.close()
        if destination_connection is not None:
            destination_connection.close()


def verify_backup(
    database_path: str | Path,
    manifest_path: str | Path | None = None,
    *,
    expected_schema_version: int = SCHEMA_VERSION,
) -> BackupVerification:
    """Verify bytes, SQLite health, migration identity, and optional manifest."""

    expected_schema_version = _closed_schema_version(expected_schema_version)
    verification = _verify_database_file(
        Path(database_path), expected_schema_version=expected_schema_version
    )
    database = Path(verification.database_path)
    if manifest_path is None:
        return verification
    manifest = Path(manifest_path).expanduser().resolve(strict=True)
    payload, manifest_hash = _load_manifest(manifest)
    _verify_manifest(
        payload,
        database_path=database,
        verification=verification,
        expected_schema_version=expected_schema_version,
    )
    return dataclasses.replace(
        verification,
        manifest_path=str(manifest),
        manifest_sha256=manifest_hash,
    )


def verify_restore_drill(
    database_path: str | Path,
    manifest_path: str | Path | None = None,
    *,
    expected_schema_version: int = SCHEMA_VERSION,
) -> RestoreDrillReceipt:
    """Verify an isolated immutable copy without constructing RuntimeStore."""

    expected_schema_version = _closed_schema_version(expected_schema_version)
    verified = verify_backup(
        database_path,
        manifest_path,
        expected_schema_version=expected_schema_version,
    )
    source = Path(verified.database_path)
    with tempfile.TemporaryDirectory(
        prefix="mastermind-executive-restore-drill-"
    ) as raw_root:
        root = Path(raw_root)
        root.chmod(0o700)
        state_directory = root / "data" / "control_plane"
        state_directory.mkdir(parents=True, mode=0o700)
        restored_path = state_directory / "executive.sqlite3"
        _copy_private_file(source, restored_path)
        _fsync_directory(state_directory)
        copied_hash = _sha256_path(restored_path)
        if copied_hash != verified.database_sha256:
            raise BackupVerificationError("restore drill copy hash differs from verified source")
        with _readonly_database(restored_path) as connection:
            _page_count, _page_size, migrations = _verify_connection(
                connection, expected_schema_version=expected_schema_version
            )
            drill_schema_digest = normalized_schema_digest(connection)
            drill_content_digest = legacy_content_digest(
                connection, expected_schema_version=expected_schema_version
            )
        if _sha256_path(restored_path) != copied_hash:
            raise BackupVerificationError("restore drill mutated the copied database")
        if any(os.path.lexists(_sidecar(restored_path, suffix)) for suffix in _SIDECAR_SUFFIXES):
            raise BackupVerificationError("restore drill created a SQLite sidecar")
        if (
            drill_schema_digest != verified.normalized_schema_digest
            or drill_content_digest != verified.legacy_content_digest
        ):
            raise BackupVerificationError(
                "restore drill schema/content digest differs from verified backup"
            )
        return RestoreDrillReceipt(
            database_sha256=verified.database_sha256,
            runtime_schema_version=expected_schema_version,
            migration_versions=tuple(item.version for item in migrations),
            normalized_schema_digest=drill_schema_digest,
            legacy_content_digest=drill_content_digest,
        )


def _marker_exists(path: Path) -> bool:
    return os.path.lexists(path)


@contextmanager
def _offline_restore_lock(
    path: Path, marker: Path, *, require_existing: bool = False
) -> Iterator[int]:
    if _marker_exists(marker):
        raise RestoreSafetyError(
            f"Executive service marker exists; stop the service first: {marker}"
        )
    if require_existing and not os.path.lexists(path):
        raise RestoreSafetyError(
            "canonical Executive service lock is missing; refuse to create a decoy"
        )
    parent = _ensure_private_directory(path.parent)
    flags = (
        os.O_RDWR
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    if not require_existing:
        flags |= os.O_CREAT
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise RestoreSafetyError(f"cannot open Executive service lock: {exc}") from exc
    try:
        info = os.fstat(descriptor)
        named = os.lstat(path)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
            or (named.st_dev, named.st_ino) != (info.st_dev, info.st_ino)
        ):
            raise RestoreSafetyError(
                "Executive service lock is not an owner-controlled file"
            )
        mode = stat.S_IMODE(info.st_mode)
        if (require_existing and mode != 0o600) or (
            not require_existing and mode & 0o077
        ):
            raise RestoreSafetyError(
                "Executive service lock is accessible to group or other"
            )
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RestoreSafetyError(
                "Executive service lock is held; stop the service first"
            ) from exc
        if _marker_exists(marker):
            raise RestoreSafetyError(
                f"Executive service marker appeared while acquiring restore lock: {marker}"
            )
        held = os.fstat(descriptor)
        named = os.lstat(path)
        if (
            held.st_nlink != 1
            or (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino)
        ):
            raise RestoreSafetyError(
                "canonical Executive service lock changed during acquisition"
            )
        yield descriptor
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
            _fsync_directory(parent)


def _sidecar(path: Path, suffix: str) -> Path:
    return path.with_name(path.name + suffix)


def _preserve_rollback_set(target: Path, rollback: Path) -> tuple[Path, ...]:
    copied: list[Path] = []
    _copy_private_file(target, rollback)
    copied.append(rollback)
    for suffix in _SIDECAR_SUFFIXES:
        source = _sidecar(target, suffix)
        if not os.path.lexists(source):
            continue
        destination = _sidecar(rollback, suffix)
        _copy_private_file(source, destination)
        copied.append(destination)
    _fsync_directory(target.parent)
    return tuple(copied)


def _remove_database_set(path: Path) -> None:
    for candidate in (path, *(_sidecar(path, suffix) for suffix in _SIDECAR_SUFFIXES)):
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass


def _restore_rollback_set(target: Path, rollback: Path) -> None:
    _remove_database_set(target)
    os.replace(rollback, target)
    for suffix in _SIDECAR_SUFFIXES:
        source = _sidecar(rollback, suffix)
        if source.exists():
            os.replace(source, _sidecar(target, suffix))
    target.chmod(0o600)
    _fsync_directory(target.parent)



def _physical_restore_state(path: Path) -> dict[str, Any]:
    """Read a stable, sidecar-free exact-v7 state without writable SQLite.

    The immutable reader cannot account for a live WAL. A checkpoint must be
    established by the incumbent stopped-owner procedure before restore; this
    reader never checkpoints, removes a sidecar, or repairs an unreadable store.
    """
    def require_sidecar_absence() -> None:
        if any(os.path.lexists(_sidecar(path, suffix)) for suffix in _SIDECAR_SUFFIXES):
            raise RestoreSafetyError(
                "physical history restore requires a verified sidecar-free database"
            )

    def identity(info: os.stat_result) -> tuple[int, ...]:
        return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    require_sidecar_absence()
    before = _assert_private_regular_file(path, label="physical history database")
    verified = _verify_database_file(path, expected_schema_version=7)
    with _readonly_database(path) as connection:
        _verify_connection(connection, expected_schema_version=7)
        history = physical_history_digest(connection)
    after = _assert_private_regular_file(path, label="physical history database")
    require_sidecar_absence()
    if identity(before) != identity(after) or _sha256_path(path) != verified.database_sha256:
        raise RestoreSafetyError("physical history database changed during observation")
    return {
        "identity": identity(after),
        "database_sha256": verified.database_sha256,
        "physical_history_digest": history,
    }


def restore_backup_offline(
    store: RuntimeStore | str | Path,
    database_path: str | Path,
    manifest_path: str | Path,
    *,
    service_marker_path: str | Path | None = None,
    service_lock_path: str | Path | None = None,
) -> RestoreReceipt:
    """Atomically restore a verified backup while the Executive service is offline.

    The service marker must be absent and the service advisory lock must be
    acquirable. The live exact-v7 database must be sidecar-free, and its complete
    physical history must exactly equal the backup and TX-9 stage. The prior
    main database remains under the returned rollback path after success.
    """

    verified = verify_backup(database_path, manifest_path)
    drill = verify_restore_drill(database_path, manifest_path)
    if drill.database_sha256 != verified.database_sha256:
        raise BackupVerificationError(
            "restore drill and backup verification hashes differ"
        )
    if (
        verified.manifest_sha256 is None
    ):  # pragma: no cover - manifest is required above
        raise BackupVerificationError("offline restore requires a verified manifest")

    # A pure root locator must not open SQLite before maintenance owns the lock.
    existing_store = store if isinstance(store, RuntimeStore) else None
    runtime_root = existing_store.root if existing_store is not None else Path(store).expanduser().absolute()
    busy_timeout_ms = existing_store.busy_timeout_ms if existing_store is not None else DEFAULT_BUSY_TIMEOUT_MS
    target_candidate = (existing_store.path if existing_store is not None
                        else runtime_root / _DB_RELATIVE_PATH)
    if not os.path.lexists(target_candidate):
        raise RestoreSafetyError(
            "Executive runtime database does not exist; refuse restore without rollback"
        )
    _assert_private_regular_file(target_candidate, label="Executive runtime database")
    target = target_candidate.resolve(strict=True)
    # Inspect the canonical upgrade barrier before the directory helper can
    # create or chmod anything in the authoritative state root.  A failed v4
    # upgrade quarantines every writer, including a RuntimeStore constructed
    # before the barrier existed.
    canonical_upgrade_barrier = target.parent / _UPGRADE_BARRIER_NAME
    if os.path.lexists(canonical_upgrade_barrier):
        raise RestoreSafetyError(
            "Executive schema upgrade barrier is present; restore is quarantined"
        )
    canonical_marker = target.parent / DEFAULT_SERVICE_MARKER_NAME
    canonical_lock = target.parent / DEFAULT_SERVICE_LOCK_NAME
    for supplied, expected, label in (
        (service_marker_path, canonical_marker, "service marker"),
        (service_lock_path, canonical_lock, "service lock"),
    ):
        if supplied is not None:
            observed = Path(supplied).expanduser().resolve(strict=False)
            if observed != expected:
                raise RestoreSafetyError(
                    f"{label} override must be the canonical runtime-state path"
                )
    runtime_directory = target.parent
    marker = canonical_marker
    lock = canonical_lock
    source = Path(verified.database_path)
    if os.path.samefile(source, target):
        raise RestoreSafetyError(
            "backup source must not be the live Executive database"
        )

    operation_id = uuid4().hex
    staged = runtime_directory / f".{target.name}.restore-{operation_id}.tmp"
    rollback = runtime_directory / f"{target.name}.pre-restore-{operation_id}"
    copied_rollback: tuple[Path, ...] = ()
    live_mutated = False
    barrier_started = False
    preserve_artifacts = False
    barrier_payload: dict[str, Any] | None = None
    barrier_identity: dict[str, Any] | None = None
    # The existing schema-upgrade barrier is the canonical writer exclusion.
    # Runtime refuses its presence regardless of the closed restore discriminator.
    with _offline_restore_lock(lock, marker) as lock_fd:
        lock_identity = _held_service_lock_identity(lock, lock_fd)
        target_before = _physical_restore_state(target)
        source_state = _physical_restore_state(source)
        if source_state["database_sha256"] != verified.database_sha256:
            raise BackupVerificationError("physical restore source changed after verification")
        physical_history = target_before["physical_history_digest"]
        if source_state["physical_history_digest"] != physical_history:
            raise RestoreSafetyError("backup would change retained physical history")
        runtime_directory = _ensure_private_directory(target.parent)

        def require_restore_custody() -> None:
            _held_service_lock_identity(lock, lock_fd, lock_identity)
            if _marker_exists(marker):
                raise RestoreSafetyError("Executive service marker appeared during restore")
            if barrier_identity is not None and barrier_payload is not None:
                _artifact_identity(canonical_upgrade_barrier,
                                   expected_payload=barrier_payload, expected=barrier_identity)

        try:
            if os.path.lexists(canonical_upgrade_barrier):
                raise RestoreSafetyError(
                    "Executive schema upgrade barrier appeared before restore staging"
                )
            _copy_private_file(source, staged)
            staged_verification = _verify_database_file(staged)
            if (
                staged_verification.database_sha256 != verified.database_sha256
                or staged_verification.database_size != verified.database_size
                or staged_verification.migrations != verified.migrations
            ):
                raise BackupVerificationError("staged restore differs from the verified backup")
            # Finish TX-9 before publishing the shared barrier: this staged
            # RuntimeStore correctly observes the same state-directory barrier.
            staged_store = RuntimeStore(runtime_root, busy_timeout_ms=busy_timeout_ms,
                                        database_path=staged)
            invalidated = Runtime.from_store(staged_store).operator_harness.invalidate_after_restore()
            final_staged = _verify_database_file(staged)
            staged_state = _physical_restore_state(staged)
            if (
                staged_state["database_sha256"] != final_staged.database_sha256
                or staged_state["physical_history_digest"] != physical_history
            ):
                raise RestoreSafetyError("TX-9 stage changed retained physical history")
            if _physical_restore_state(target) != target_before:
                raise RestoreSafetyError("live physical history source changed before rollback copy")
            copied_rollback = _preserve_rollback_set(target, rollback)
            rollback_state = _physical_restore_state(rollback)
            if (
                rollback_state["database_sha256"] != target_before["database_sha256"]
                or rollback_state["physical_history_digest"] != physical_history
            ):
                raise RestoreSafetyError("rollback copy changed retained physical history")
            require_restore_custody()
            if os.path.lexists(canonical_upgrade_barrier):
                raise RestoreSafetyError(
                    "Executive schema upgrade barrier appeared before database replacement"
                )
            if _physical_restore_state(target) != target_before:
                raise RestoreSafetyError("live physical history changed before database replacement")
            barrier_payload = {
                "schema_version": RESTORE_BARRIER_SCHEMA,
                "operation_id": operation_id,
                "database_path": str(target),
                "target_preimage": target_before,
                "source_backup_path": str(source),
                "source_backup_sha256": verified.database_sha256,
                "manifest_sha256": verified.manifest_sha256,
                "staged_path": str(staged),
                "staged_state": staged_state,
                "rollback_path": str(rollback),
                "rollback_state": rollback_state,
                "physical_history_digest": physical_history,
                "control_uid": os.geteuid(),
                "created_at": _utc_now(),
            }
            # Once publication may begin, an incomplete barrier stays occupied.
            # A crash also retains both staged and rollback evidence.
            barrier_started = True
            preserve_artifacts = True
            _write_private_json(canonical_upgrade_barrier, barrier_payload)
            barrier_identity = _artifact_identity(
                canonical_upgrade_barrier, expected_payload=barrier_payload
            )
            require_restore_custody()
            if _physical_restore_state(target) != target_before:
                raise RestoreSafetyError("live source changed after restore barrier publication")
            if _physical_restore_state(staged) != staged_state:
                raise RestoreSafetyError("qualified restore stage changed before replacement")
            if _physical_restore_state(rollback) != rollback_state:
                raise RestoreSafetyError("qualified rollback changed before replacement")
            # No sidecars are removed. Their absence is proved and the barrier
            # prevents ordinary Runtime writers from recreating one.
            live_mutated = True
            os.replace(staged, target)
            target.chmod(0o600)
            _fsync_directory(runtime_directory)
            restored = _verify_database_file(target)
            restored_state = _physical_restore_state(target)
            if (
                restored.database_sha256 != final_staged.database_sha256
                or restored_state["database_sha256"] != final_staged.database_sha256
                or restored_state["physical_history_digest"] != physical_history
            ):
                raise BackupVerificationError("restored database differs from qualified TX-9 stage")
            require_restore_custody()
            _unlink_exact_upgrade_artifact(
                canonical_upgrade_barrier, expected_payload=barrier_payload,
                expected=barrier_identity,
            )
            preserve_artifacts = False
            if existing_store is not None:
                existing_store._schema_ready = False
            return RestoreReceipt(
                restored_database_path=str(target),
                restored_sha256=restored.database_sha256,
                rollback_database_path=str(rollback),
                rollback_sidecar_paths=tuple(str(path) for path in copied_rollback if path != rollback),
                rollback_sha256=rollback_state["database_sha256"],
                manifest_sha256=verified.manifest_sha256,
                restored_at=_utc_now(),
                source_backup_sha256=verified.database_sha256,
                final_runtime_sha256=restored.database_sha256,
                ohf_invalidated_attempts=invalidated,
                physical_history_digest=physical_history,
            )
        except Exception as exc:
            if barrier_started:
                try:
                    if barrier_identity is None or barrier_payload is None:
                        raise RestoreSafetyError("restore barrier publication is incomplete")
                    # A lost canonical lock never authorizes destructive rollback.
                    require_restore_custody()
                    if live_mutated:
                        if _physical_restore_state(rollback) != rollback_state:
                            raise RestoreSafetyError("rollback artifact changed before recovery")
                        require_restore_custody()
                        _restore_rollback_set(target, rollback)
                        if existing_store is not None:
                            existing_store._schema_ready = False
                        rollback_proof = _physical_restore_state(target)
                        if (
                            rollback_proof["database_sha256"] != target_before["database_sha256"]
                            or rollback_proof["physical_history_digest"] != physical_history
                        ):
                            raise BackupVerificationError("rollback failed physical history conservation")
                    elif _physical_restore_state(target) != target_before:
                        raise RestoreSafetyError("pre-effect restore target changed")
                    require_restore_custody()
                    _unlink_exact_upgrade_artifact(
                        canonical_upgrade_barrier, expected_payload=barrier_payload,
                        expected=barrier_identity,
                    )
                except Exception as guard_exc:
                    preserve_artifacts = True
                    if barrier_payload is not None:
                        _ensure_upgrade_quarantine_barrier(canonical_upgrade_barrier, barrier_payload)
                    raise RestoreRollbackError(
                        "restore effect or custody remains unknown; writer barrier and evidence retained"
                    ) from guard_exc
                preserve_artifacts = False
                if live_mutated:
                    raise RestoreRollbackError(
                        "restore mutation failed; previous database bytes were restored"
                    ) from exc
            for path in copied_rollback:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            raise
        finally:
            if not preserve_artifacts:
                try:
                    staged.unlink()
                except FileNotFoundError:
                    pass


def _upgrade_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _upgrade_digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _upgrade_hook(phase: str) -> None:
    hook = _SCHEMA_UPGRADE_TEST_HOOK
    if hook is not None:
        hook(phase)


def _default_upgrade_release_observer() -> Mapping[str, str]:
    source = Path(__file__).resolve(strict=True)
    release_root = source.parents[1]
    info = release_root.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ExecutiveSchemaUpgradeError("installed release root is not a real directory")
    release_sha = release_root.name
    if _GIT_SHA_RE.fullmatch(release_sha) is None:
        raise ExecutiveSchemaUpgradeError(
            "schema upgrader is not running from an exact-SHA installed release"
        )
    try:
        from ops.executive_os import release_manifest

        manifest_path = release_root / release_manifest.MANIFEST_NAME
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        tree_sha = str(raw.get("tree_sha") or "")
        verified = release_manifest.verify(release_root, release_sha, tree_sha)
    except Exception as exc:
        raise ExecutiveSchemaUpgradeError(
            "installed release manifest proof failed"
        ) from exc
    if verified.get("commit_sha") != release_sha or _GIT_SHA_RE.fullmatch(tree_sha) is None:
        raise ExecutiveSchemaUpgradeError("installed release manifest identity is invalid")
    return {
        "release_root": str(release_root),
        "release_sha": release_sha,
        "release_tree_sha": tree_sha,
        "release_manifest_sha256": _sha256_path(manifest_path),
    }


def _prove_upgrade_release(expected_sha: str) -> dict[str, str]:
    expected = str(expected_sha or "").strip()
    if _GIT_SHA_RE.fullmatch(expected) is None:
        raise ExecutiveSchemaUpgradeError(
            "release_sha must be an exact lowercase 40-hex Git SHA"
        )
    observer = _SCHEMA_UPGRADE_RELEASE_OBSERVER or _default_upgrade_release_observer
    observed = observer()
    if not isinstance(observed, Mapping) or set(observed) != {
        "release_root",
        "release_sha",
        "release_tree_sha",
        "release_manifest_sha256",
    }:
        raise ExecutiveSchemaUpgradeError("installed release observation is malformed")
    root = Path(str(observed["release_root"]))
    try:
        info = root.lstat()
    except OSError as exc:
        raise ExecutiveSchemaUpgradeError("installed release root is unavailable") from exc
    if (
        not root.is_absolute()
        or stat.S_ISLNK(info.st_mode)
        or not stat.S_ISDIR(info.st_mode)
        or root.resolve(strict=True) != root
        or root.name != expected
        or observed["release_sha"] != expected
        or _GIT_SHA_RE.fullmatch(str(observed["release_tree_sha"])) is None
        or _HASH_RE.fullmatch(str(observed["release_manifest_sha256"])) is None
    ):
        raise ExecutiveSchemaUpgradeError(
            "running installed release does not match release_sha"
        )
    return {
        "release_root": str(root),
        "release_sha": expected,
        "release_tree_sha": str(observed["release_tree_sha"]),
        "release_manifest_sha256": str(observed["release_manifest_sha256"]),
    }


def _upgrade_receipt_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _artifact_identity(
    path: Path,
    *,
    expected_payload: Mapping[str, Any],
    expected: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ExecutiveSchemaUpgradeError(f"upgrade artifact is unavailable: {path}") from exc
    try:
        info = os.fstat(descriptor)
        named = os.lstat(path)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
            or (named.st_dev, named.st_ino) != (info.st_dev, info.st_ino)
        ):
            raise ExecutiveSchemaUpgradeError(
                f"upgrade artifact is not an exact owner-only regular file: {path}"
            )
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_MANIFEST_BYTES:
                raise ExecutiveSchemaUpgradeError(f"upgrade artifact is oversized: {path}")
            chunks.append(chunk)
        payload = b"".join(chunks)
    finally:
        os.close(descriptor)
    if len(payload) > _MAX_MANIFEST_BYTES or payload != _upgrade_receipt_bytes(expected_payload):
        raise ExecutiveSchemaUpgradeError(f"upgrade artifact bytes changed: {path}")
    identity = {
        "path": str(path),
        "device": int(info.st_dev),
        "inode": int(info.st_ino),
        "size": int(info.st_size),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "payload_digest": _upgrade_digest(expected_payload),
    }
    if expected is not None and dict(expected) != identity:
        raise ExecutiveSchemaUpgradeError(f"upgrade artifact identity changed: {path}")
    return identity


def _unlink_exact_upgrade_artifact(
    path: Path, *, expected_payload: Mapping[str, Any], expected: Mapping[str, Any]
) -> None:
    # The state directory is owner-only and the independent census has just
    # proved no second control-UID process.  Hold the inode while unlinking and
    # prove that the held inode, rather than a replacement, lost its name.
    _artifact_identity(path, expected_payload=expected_payload, expected=expected)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        held = os.fstat(descriptor)
        if (held.st_dev, held.st_ino) != (expected["device"], expected["inode"]):
            raise ExecutiveSchemaUpgradeError("upgrade artifact changed before unlink")
        path.unlink()
        if os.fstat(descriptor).st_nlink != 0:
            raise ExecutiveSchemaUpgradeError("upgrade artifact unlink did not remove held inode")
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def _ensure_upgrade_quarantine_barrier(
    path: Path, payload: Mapping[str, Any]
) -> None:
    if os.path.lexists(path):
        return
    try:
        _write_private_json(path, payload)
    except FileExistsError:
        pass
    if not os.path.lexists(path):
        raise ExecutiveSchemaUpgradeError(
            "cannot restore the durable schema-upgrade quarantine barrier"
        )


def _held_service_lock_identity(
    path: Path, descriptor: int, expected: Mapping[str, int] | None = None
) -> dict[str, int]:
    held = os.fstat(descriptor)
    named = os.lstat(path)
    identity = {
        "device": int(held.st_dev),
        "inode": int(held.st_ino),
        "mode": stat.S_IMODE(held.st_mode),
        "uid": int(held.st_uid),
        "links": int(held.st_nlink),
    }
    if (
        not stat.S_ISREG(held.st_mode)
        or (named.st_dev, named.st_ino) != (held.st_dev, held.st_ino)
        or identity["mode"] != 0o600
        or identity["uid"] != os.geteuid()
        or identity["links"] != 1
        or (expected is not None and dict(expected) != identity)
    ):
        raise RestoreSafetyError("canonical Executive service lock identity changed")
    return identity


def _checkpoint_quiesced_wal(database: Path) -> None:
    connection = sqlite3.connect(database, isolation_level=None, timeout=5.0)
    try:
        row = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if row is not None and (type(row[0]) is not int or row[0] != 0):
            raise RestoreSafetyError("Executive WAL checkpoint reports a busy writer")
    finally:
        connection.close()
    lingering = [
        str(_sidecar(database, suffix))
        for suffix in _SIDECAR_SUFFIXES
        if os.path.lexists(_sidecar(database, suffix))
    ]
    if lingering:
        raise RestoreSafetyError(
            "Executive database retains sidecars after quiesced checkpoint: "
            + ", ".join(lingering)
        )


def _run_census_command(argv: list[str]) -> tuple[int, str, str, int]:
    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
        )
    except FileNotFoundError as exc:
        raise RestoreSafetyError("independent census tool is unavailable") from exc
    try:
        stdout, stderr = process.communicate(timeout=10)
    except BaseException:
        process.kill()
        process.wait()
        raise
    if len(stdout.encode("utf-8")) > 512 * 1024 or len(stderr.encode("utf-8")) > 64 * 1024:
        raise RestoreSafetyError("writer census output exceeded its closed bound")
    return int(process.returncode), stdout, stderr, int(process.pid)


def _parse_census_ps_uid(value: str) -> int:
    """Decode ps presentation into the exact unsigned 32-bit kernel UID.

    Darwin ps uses signed decimal UIDFMT for uid_t fields.  Normalizing that
    representation preserves UID equality; it never excludes a process row.
    Other platforms retain unsigned-only input.  Bounds precede int parsing.
    """
    if re.fullmatch(r"[0-9]{1,10}", value) is not None:
        uid = int(value)
        if uid <= 0xFFFFFFFF:
            return uid
    elif sys.platform == "darwin" and re.fullmatch(r"-[1-9][0-9]{0,9}", value) is not None:
        uid = int(value)
        if -(1 << 31) <= uid < 0:
            return uid + (1 << 32)
    raise RestoreSafetyError("independent process census is malformed")


def _default_upgrade_census(database: Path, lock: Path, barrier: Path, lock_fd: int) -> Mapping[str, Any]:
    return _default_upgrade_census_with_context(database, lock, barrier, lock_fd)


def _default_upgrade_census_with_context(
    database: Path, lock: Path, barrier: Path, lock_fd: int,
    _recovery: _PreCensusContinuation | None = None,
) -> Mapping[str, Any]:
    control_uids = sorted(
        set(
            os.getresuid()
            if hasattr(os, "getresuid")
            else (os.getuid(), os.geteuid())
        )
    )
    # The complete argv for every process is unbounded input: long-lived agent
    # hosts can legitimately push ``ps ... command=`` beyond the census wire's
    # 512 KiB fail-closed limit even when no process shares the control UID.
    # Only UID membership affects admission below.  Keep one bounded executable
    # identity for the adverse-process diagnostic digest without collecting
    # unrelated processes' arguments.
    ps_status, ps_output, ps_error, ps_pid = _run_census_command(
        ["/bin/ps", "-axo", "pid=,svuid=,ruid=,uid=,comm="]
    )
    if ps_status != 0 or ps_error:
        raise RestoreSafetyError("independent process census failed closed")
    process_rows: list[dict[str, Any]] = []
    upgrader_observed = False
    sensor_child_observed = False
    for line in ps_output.splitlines():
        parts = line.strip().split(None, 4)
        if len(parts) != 5 or re.fullmatch(r"[0-9]{1,10}", parts[0]) is None:
            raise RestoreSafetyError("independent process census is malformed")
        pid = int(parts[0])
        if not 0 < pid < (1 << 31):
            raise RestoreSafetyError("independent process census is malformed")
        observed_uids = {_parse_census_ps_uid(value) for value in parts[1:4]}
        if pid == os.getpid():
            if upgrader_observed or not observed_uids & set(control_uids):
                raise RestoreSafetyError("process census upgrader sentinel is malformed")
            upgrader_observed = True
        elif pid == ps_pid:
            if sensor_child_observed or not observed_uids & set(control_uids):
                raise RestoreSafetyError("process census child sentinel is malformed")
            sensor_child_observed = True
        elif observed_uids & set(control_uids):
            process_rows.append(
                {
                    "pid": pid,
                    "uids": sorted(observed_uids),
                    "command_sha256": hashlib.sha256(parts[4].encode("utf-8")).hexdigest(),
                }
            )
    if not upgrader_observed or not sensor_child_observed:
        raise RestoreSafetyError("independent process census omitted a required sentinel")
    if process_rows:
        raise RestoreSafetyError("another control-UID process exists during upgrade")

    inspected = [
        str(database),
        *(str(_sidecar(database, suffix)) for suffix in _SIDECAR_SUFFIXES),
        str(lock),
        str(barrier),
    ]
    existing = [path for path in inspected if os.path.lexists(path)]
    lsof = Path("/usr/sbin/lsof")
    # ``lsof`` otherwise emits host-global mount warnings on stderr (for
    # example, an unrelated App Translocation nullfs that it cannot stat).
    # Suppress warnings at the sensor while retaining its exit status and the
    # closed machine-readable rows for the exact inspected paths.
    status, output, error, _lsof_pid = _run_census_command(
        [str(lsof), "-w", "-nP", "-F", "pufn", "--", *existing]
    )
    # Darwin lsof exits 1 when at least one named path has no matching open
    # descriptor, even when it emits the complete row for another named path.
    # The closed parser below still requires exactly our held lock descriptor;
    # accept only that ordinary partial/no-match status and no diagnostics.
    if status not in (0, 1) or error:
        raise RestoreSafetyError("independent file census failed closed")
    file_rows: list[dict[str, Any]] = []
    current_pid: int | None = None
    current_uid: int | None = None
    current_fd: str | None = None
    for line in output.splitlines():
        if not line:
            continue
        tag, value = line[0], line[1:]
        if tag == "p":
            if not value.isdigit():
                raise RestoreSafetyError("file census pid is malformed")
            current_pid, current_uid, current_fd = int(value), None, None
        elif tag == "u":
            if current_pid is None or not value.isdigit():
                raise RestoreSafetyError("file census uid is malformed")
            current_uid = int(value)
        elif tag == "f":
            if current_pid is None or re.fullmatch(r"[0-9]+[A-Za-z]*", value) is None:
                raise RestoreSafetyError("file census descriptor is malformed")
            current_fd = value
        elif tag == "n":
            if current_pid is None or current_uid is None or current_fd is None:
                raise RestoreSafetyError("file census row is incomplete")
            row = {
                "pid": current_pid,
                "uid": current_uid,
                "fd": current_fd,
                "path": value,
            }
            file_rows.append(row)
        else:
            raise RestoreSafetyError("file census contains an unknown field")
    expected_rows = ([{"pid": os.getpid(), "uid": os.geteuid(),
                       "fd": str(lock_fd), "path": str(lock)}]
                     if _recovery is None else _recovery.census_rows())
    expected_by_fd = {int(row["fd"]): row for row in expected_rows}
    if len(file_rows) != len(expected_rows):
        raise RestoreSafetyError("independent file census omitted or duplicated a held sentinel")
    for row in file_rows:
        fd_number = re.match(r"[0-9]+", str(row["fd"]))
        if (
            fd_number is None
            or int(fd_number.group()) not in expected_by_fd
            or any(row[key] != expected_by_fd[int(fd_number.group())][key]
                   for key in ("pid", "uid", "path"))
        ):
            raise RestoreSafetyError("independent file census found another open runtime file")
        # lsof decorates descriptors with access-mode suffixes (for example
        # ``3u``).  Persist the closed numeric identity used by repeated census
        # comparison rather than a presentation detail of the sensor.
        row["fd"] = str(int(fd_number.group()))
    file_rows.sort(key=lambda row: int(row["fd"]))
    if file_rows != expected_rows:
        raise RestoreSafetyError("independent file census repeated or changed a held sentinel")
    if _recovery is not None:
        _recovery.census_rows()
    return {
        "schema_version": UPGRADE_CENSUS_SCHEMA if _recovery is None else PRE_CENSUS_CENSUS_SCHEMA,
        "control_uids": control_uids,
        "upgrader_pid": os.getpid(),
        "inspected_paths": inspected,
        "process_sensor": {
            "binary": "/bin/ps",
            "upgrader_observed": True,
            "sensor_child_observed": True,
        },
        "file_sensor": {
            "binary": "/usr/sbin/lsof",
            "held_lock_observed": True,
        },
        "processes": [],
        "open_files": file_rows,
    }


def _upgrade_census(
    database: Path, lock: Path, barrier: Path, lock_fd: int
) -> dict[str, Any]:
    observer = _SCHEMA_UPGRADE_CENSUS_OBSERVER or _default_upgrade_census
    raw = observer(database, lock, barrier, lock_fd)
    return _validate_upgrade_census(raw, database, lock, barrier, lock_fd)


def _validate_upgrade_census(raw: Any, database: Path, lock: Path, barrier: Path,
                            lock_fd: int, _recovery: _PreCensusContinuation | None = None) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or set(raw) != {
        "schema_version",
        "control_uids",
        "upgrader_pid",
        "inspected_paths",
        "process_sensor",
        "file_sensor",
        "processes",
        "open_files",
    }:
        raise RestoreSafetyError("writer census material is not the closed wire")
    material = dict(raw)
    expected_paths = [
        str(database),
        *(str(_sidecar(database, suffix)) for suffix in _SIDECAR_SUFFIXES),
        str(lock),
        str(barrier),
    ]
    if (
        material["schema_version"] != (UPGRADE_CENSUS_SCHEMA if _recovery is None else PRE_CENSUS_CENSUS_SCHEMA)
        or material["control_uids"]
        != sorted(
            set(
                os.getresuid()
                if hasattr(os, "getresuid")
                else (os.getuid(), os.geteuid())
            )
        )
        or material["upgrader_pid"] != os.getpid()
        or material["process_sensor"]
        != {
            "binary": "/bin/ps",
            "upgrader_observed": True,
            "sensor_child_observed": True,
        }
        or material["file_sensor"]
        != {
            "binary": "/usr/sbin/lsof",
            "held_lock_observed": True,
        }
        or material["processes"] != []
        or material["inspected_paths"] != expected_paths
        or material["open_files"] != (
            [{"pid": os.getpid(), "uid": os.geteuid(), "fd": str(lock_fd), "path": str(lock)}]
            if _recovery is None else _recovery.census_rows())
    ):
        raise RestoreSafetyError("writer census material is adverse")
    for row in material["open_files"]:
        if (
            not isinstance(row, dict)
            or set(row) != {"pid", "uid", "fd", "path"}
            or type(row["pid"]) is not int
            or type(row["uid"]) is not int
            or not isinstance(row["fd"], str)
            or not isinstance(row["path"], str)
        ):
            raise RestoreSafetyError("writer file census row is malformed")
    _canonical_bytes(material)
    return material


def _upgrade_database_state(database: Path, *, version: int) -> dict[str, Any]:
    if any(
        os.path.lexists(_sidecar(database, suffix)) for suffix in _SIDECAR_SUFFIXES
    ):
        raise ExecutiveSchemaUpgradeError(
            "authoritative database has a SQLite sidecar during exact upgrade proof"
        )
    info = _assert_private_regular_file(database, label=f"Executive exact-v{version} database")
    verified = verify_backup(database, expected_schema_version=version)
    state = {
        "database": {
            "path": str(database),
            "device": int(info.st_dev),
            "inode": int(info.st_ino),
            "size": int(info.st_size),
            "sha256": verified.database_sha256,
        },
        "migration_vector": [item.to_dict() for item in verified.migrations],
        "normalized_schema_digest": verified.normalized_schema_digest,
        "legacy_content_digest": verified.legacy_content_digest,
    }
    if version >= 4:
        with _readonly_database(database) as connection:
            state["full_v4_content_digest"] = full_v4_content_digest(connection)
            if version >= 5:
                state["full_v5_content_digest"] = full_v5_content_digest(connection)
            if version >= 6:
                state["full_v6_content_digest"] = full_v6_content_digest(connection)
            if version >= 7:
                state["physical_history_digest"] = physical_history_digest(connection)
    return state


def _rollback_reproduces_preflight(
    current: Mapping[str, Any], before: Mapping[str, Any]
) -> bool:
    current_database = current.get("database")
    before_database = before.get("database")
    return bool(
        isinstance(current_database, Mapping)
        and isinstance(before_database, Mapping)
        and {
            key: current_database.get(key) for key in ("path", "device", "inode")
        }
        == {key: before_database.get(key) for key in ("path", "device", "inode")}
        and current.get("migration_vector") == before.get("migration_vector")
        and current.get("normalized_schema_digest")
        == before.get("normalized_schema_digest")
        and current.get("legacy_content_digest") == before.get("legacy_content_digest")
        and current.get("full_v4_content_digest")
        == before.get("full_v4_content_digest")
        and current.get("full_v5_content_digest") == before.get("full_v5_content_digest")
        and current.get("full_v6_content_digest") == before.get("full_v6_content_digest")
        and current.get("physical_history_digest") == before.get("physical_history_digest")
    )


def _assert_upgrade_database_inode(
    database: Path, before: Mapping[str, Any]
) -> None:
    expected = before.get("database")
    if not isinstance(expected, Mapping):
        raise ExecutiveSchemaUpgradeError("preflight database identity is malformed")
    info = _assert_private_regular_file(database, label="Executive upgrade database")
    if (
        str(database) != expected.get("path")
        or (int(info.st_dev), int(info.st_ino))
        != (expected.get("device"), expected.get("inode"))
    ):
        raise ExecutiveSchemaUpgradeError("authoritative database inode changed during upgrade")


def upgrade_v3_to_v4(
    database_path: str | Path,
    backup_directory: str | Path,
    *,
    release_sha: str,
) -> SchemaUpgradeReceipt:
    """Perform the sole explicit, offline, forward-only exact-v3→v4 upgrade."""

    release = _prove_upgrade_release(release_sha)
    candidate = Path(database_path).expanduser()
    _assert_private_regular_file(candidate, label="Executive exact-v3 database")
    database = candidate.resolve(strict=True)
    state_directory = database.parent
    marker = state_directory / DEFAULT_SERVICE_MARKER_NAME
    lock = state_directory / DEFAULT_SERVICE_LOCK_NAME
    barrier = state_directory / _UPGRADE_BARRIER_NAME
    preflight_path = state_directory / _UPGRADE_PREFLIGHT_NAME
    completion_path = state_directory / _UPGRADE_COMPLETION_NAME
    if any(os.path.lexists(path) for path in (barrier, preflight_path, completion_path)):
        raise ExecutiveSchemaUpgradeError(
            "upgrade barrier/receipt already exists; inspect before recovery"
        )
    operation_id = uuid4().hex
    created_at = _upgrade_now()
    barrier_payload = {
        "schema_version": UPGRADE_BARRIER_SCHEMA,
        "operation_id": operation_id,
        "database_path": str(database),
        "tool_release_root": release["release_root"],
        "tool_release_tree_sha": release["release_tree_sha"],
        "tool_release_manifest_sha256": release["release_manifest_sha256"],
        "release_sha": release["release_sha"],
        "control_uid": os.geteuid(),
        "created_at": created_at,
    }
    before: dict[str, Any] | None = None
    preflight: dict[str, Any] | None = None
    barrier_identity: dict[str, Any] | None = None
    preflight_identity: dict[str, Any] | None = None
    census: dict[str, Any] | None = None
    committed_v4 = False
    with _offline_restore_lock(lock, marker, require_existing=True) as lock_fd:
        lock_identity = _held_service_lock_identity(lock, lock_fd)
        _write_private_json(barrier, barrier_payload)
        barrier_identity = _artifact_identity(
            barrier, expected_payload=barrier_payload
        )
        try:
            _upgrade_hook("barrier_persisted")
            _artifact_identity(
                barrier,
                expected_payload=barrier_payload,
                expected=barrier_identity,
            )
            if _marker_exists(marker):
                raise RestoreSafetyError("Executive service marker appeared before census")
            census = _upgrade_census(database, lock, barrier, lock_fd)
            _checkpoint_quiesced_wal(database)
            if _upgrade_census(database, lock, barrier, lock_fd) != census:
                raise RestoreSafetyError("writer census changed across WAL checkpoint")
            before = _upgrade_database_state(database, version=3)
            v3_backup = create_offline_backup(
                database, backup_directory, expected_schema_version=3
            )
            v3_drill = verify_restore_drill(
                v3_backup.database_path,
                v3_backup.manifest_path,
                expected_schema_version=3,
            )
            if (
                v3_backup.legacy_content_digest != before["legacy_content_digest"]
                or v3_drill.legacy_content_digest != before["legacy_content_digest"]
                or v3_backup.normalized_schema_digest
                != before["normalized_schema_digest"]
                or v3_drill.normalized_schema_digest
                != before["normalized_schema_digest"]
            ):
                raise ExecutiveSchemaUpgradeError("v3 source/backup/drill proof differs")
            preflight = {
                "schema_version": UPGRADE_PREFLIGHT_SCHEMA,
                "operation_id": operation_id,
                "database": before["database"],
                "migration_vector": before["migration_vector"],
                "normalized_schema_digest": before["normalized_schema_digest"],
                "pre_v4_legacy_content_digest": before["legacy_content_digest"],
                "barrier_identity": barrier_identity,
                "v3_backup": {
                    "database_path": v3_backup.database_path,
                    "database_sha256": v3_backup.database_sha256,
                    "manifest_path": v3_backup.manifest_path,
                    "manifest_sha256": v3_backup.manifest_sha256,
                    "restore_drill_receipt": v3_drill.to_dict(),
                    "restore_drill_digest": _upgrade_digest(v3_drill.to_dict()),
                },
                "quiesce_writer_census": census,
                "quiesce_writer_census_digest": _upgrade_digest(census),
                "tool_release_root": release["release_root"],
                "tool_release_tree_sha": release["release_tree_sha"],
                "tool_release_manifest_sha256": release[
                    "release_manifest_sha256"
                ],
                "release_sha": release["release_sha"],
                "created_at": created_at,
            }
            _write_private_json(preflight_path, preflight)
            preflight_identity = _artifact_identity(
                preflight_path, expected_payload=preflight
            )
            preflight_digest = _upgrade_digest(preflight)
            _upgrade_hook("preflight_persisted")

            def revalidate_control_artifacts() -> None:
                if _marker_exists(marker):
                    raise RestoreSafetyError(
                        "Executive service marker appeared during schema upgrade"
                    )
                _held_service_lock_identity(lock, lock_fd, lock_identity)
                _artifact_identity(
                    barrier,
                    expected_payload=barrier_payload,
                    expected=barrier_identity,
                )
                _artifact_identity(
                    preflight_path,
                    expected_payload=preflight,
                    expected=preflight_identity,
                )
                if _prove_upgrade_release(release_sha) != release:
                    raise ExecutiveSchemaUpgradeError("tool release identity changed")
                _assert_upgrade_database_inode(database, before)

            def revalidate_v3_backup_proof() -> None:
                checked = verify_backup(
                    v3_backup.database_path,
                    v3_backup.manifest_path,
                    expected_schema_version=3,
                )
                checked_drill = verify_restore_drill(
                    v3_backup.database_path,
                    v3_backup.manifest_path,
                    expected_schema_version=3,
                )
                if (
                    checked.database_sha256 != v3_backup.database_sha256
                    or checked.manifest_sha256 != v3_backup.manifest_sha256
                    or checked.normalized_schema_digest
                    != v3_backup.normalized_schema_digest
                    or checked.legacy_content_digest
                    != v3_backup.legacy_content_digest
                    or checked_drill.to_dict() != v3_drill.to_dict()
                    or _upgrade_digest(checked_drill.to_dict())
                    != preflight["v3_backup"]["restore_drill_digest"]
                ):
                    raise ExecutiveSchemaUpgradeError(
                        "v3 backup or restore-drill proof changed after preflight"
                    )

            revalidate_control_artifacts()
            revalidate_v3_backup_proof()
            if _upgrade_database_state(database, version=3) != before:
                raise ExecutiveSchemaUpgradeError("v3 source changed after preflight")
            if _upgrade_census(database, lock, barrier, lock_fd) != census:
                raise RestoreSafetyError("writer census changed before migration")

            connection = sqlite3.connect(database, isolation_level=None, timeout=5.0)
            connection.row_factory = sqlite3.Row
            try:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("BEGIN EXCLUSIVE")
                revalidate_control_artifacts()
                _verify_connection(connection, expected_schema_version=3)
                if legacy_content_digest(
                    connection, expected_schema_version=3
                ) != before["legacy_content_digest"]:
                    raise ExecutiveSchemaUpgradeError("in-transaction v3 content changed")
                _upgrade_hook("exclusive_v3_verified")
                revalidate_control_artifacts()
                version, name, statements = _MIGRATIONS[3]
                if version != 4:
                    raise ExecutiveSchemaUpgradeError("reviewed migration 4 is unavailable")
                for ordinal, statement in enumerate(statements, 1):
                    connection.execute(statement)
                    _upgrade_hook(f"after_m4_statement:{ordinal:02d}")
                    revalidate_control_artifacts()
                connection.execute(
                    """
                    INSERT INTO schema_migrations(version,name,checksum,applied_at_ms)
                    VALUES(?,?,?,?)
                    """,
                    (
                        version,
                        name,
                        _migration_checksum(statements),
                        int(datetime.now(UTC).timestamp() * 1000),
                    ),
                )
                _upgrade_hook("after_m4_receipt")
                revalidate_control_artifacts()
                _verify_connection(connection, expected_schema_version=4)
                if legacy_content_digest(
                    connection, expected_schema_version=4
                ) != before["legacy_content_digest"]:
                    raise ExecutiveSchemaUpgradeError("migration changed legacy content")
                _upgrade_hook("before_v4_commit")
                revalidate_control_artifacts()
                _verify_connection(connection, expected_schema_version=4)
                if legacy_content_digest(
                    connection, expected_schema_version=4
                ) != before["legacy_content_digest"]:
                    raise ExecutiveSchemaUpgradeError("precommit legacy content drifted")
                connection.commit()
                committed_v4 = True
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()

            _upgrade_hook("after_v4_commit_before_checkpoint")
            revalidate_control_artifacts()
            _checkpoint_quiesced_wal(database)
            _upgrade_hook("after_v4_checkpoint")
            revalidate_control_artifacts()
            verified_v4 = _upgrade_database_state(database, version=4)
            if verified_v4["legacy_content_digest"] != before["legacy_content_digest"]:
                raise ExecutiveSchemaUpgradeError("committed v4 legacy content differs")
            v4_backup = create_offline_backup(
                database, backup_directory, expected_schema_version=4
            )
            v4_drill = verify_restore_drill(
                v4_backup.database_path,
                v4_backup.manifest_path,
                expected_schema_version=4,
            )
            if (
                v4_backup.legacy_content_digest != before["legacy_content_digest"]
                or v4_drill.legacy_content_digest != before["legacy_content_digest"]
                or v4_backup.normalized_schema_digest
                != verified_v4["normalized_schema_digest"]
                or v4_drill.normalized_schema_digest
                != verified_v4["normalized_schema_digest"]
            ):
                raise ExecutiveSchemaUpgradeError("v4 source/backup/drill proof differs")
            if _upgrade_census(database, lock, barrier, lock_fd) != census:
                raise RestoreSafetyError("writer census changed before completion")
            revalidate_control_artifacts()
            completed_at = _upgrade_now()
            completion = {
                "schema_version": UPGRADE_COMPLETION_SCHEMA,
                "operation_id": operation_id,
                "preflight_receipt_digest": preflight_digest,
                "authoritative_v4_database": verified_v4["database"],
                "authoritative_v4_schema_digest": verified_v4[
                    "normalized_schema_digest"
                ],
                "migration_vector": verified_v4["migration_vector"],
                "pre_v4_legacy_content_digest": before["legacy_content_digest"],
                "post_v4_legacy_content_digest": verified_v4[
                    "legacy_content_digest"
                ],
                "legacy_content_equal": True,
                "v4_backup": {
                    "database_path": v4_backup.database_path,
                    "database_sha256": v4_backup.database_sha256,
                    "manifest_path": v4_backup.manifest_path,
                    "manifest_sha256": v4_backup.manifest_sha256,
                    "restore_drill_receipt": v4_drill.to_dict(),
                    "restore_drill_digest": _upgrade_digest(v4_drill.to_dict()),
                },
                "tx9_preservation_digest": verified_v4["legacy_content_digest"],
                "quiesce_writer_census_digest": _upgrade_digest(census),
                "tool_release_root": release["release_root"],
                "tool_release_tree_sha": release["release_tree_sha"],
                "tool_release_manifest_sha256": release[
                    "release_manifest_sha256"
                ],
                "release_sha": release["release_sha"],
                "completed_at": completed_at,
            }
            _write_private_json(completion_path, completion)
            completion_identity = _artifact_identity(
                completion_path, expected_payload=completion
            )
            _upgrade_hook("completion_persisted")
            # The final adversarial seam is deliberately placed before the
            # complete authoritative/backup/drill/census proof.  Nothing after
            # this hook may escape revalidation before the barrier is removed.
            _upgrade_hook("before_barrier_unlink")
            revalidate_control_artifacts()
            _artifact_identity(
                completion_path,
                expected_payload=completion,
                expected=completion_identity,
            )
            final_v4 = _upgrade_database_state(database, version=4)
            final_v4_backup = verify_backup(
                v4_backup.database_path,
                v4_backup.manifest_path,
                expected_schema_version=4,
            )
            final_v4_drill = verify_restore_drill(
                v4_backup.database_path,
                v4_backup.manifest_path,
                expected_schema_version=4,
            )
            if (
                final_v4 != verified_v4
                or final_v4_backup.database_sha256 != v4_backup.database_sha256
                or final_v4_backup.manifest_sha256 != v4_backup.manifest_sha256
                or final_v4_backup.normalized_schema_digest
                != v4_backup.normalized_schema_digest
                or final_v4_backup.legacy_content_digest
                != v4_backup.legacy_content_digest
                or final_v4_drill.to_dict() != v4_drill.to_dict()
                or _upgrade_digest(final_v4_drill.to_dict())
                != completion["v4_backup"]["restore_drill_digest"]
            ):
                raise ExecutiveSchemaUpgradeError(
                    "completion v4 source/backup/drill proof changed"
                )
            if _upgrade_census(database, lock, barrier, lock_fd) != census:
                raise RestoreSafetyError("writer census changed before barrier release")
            revalidate_control_artifacts()
            _artifact_identity(
                completion_path,
                expected_payload=completion,
                expected=completion_identity,
            )
            _unlink_exact_upgrade_artifact(
                barrier,
                expected_payload=barrier_payload,
                expected=barrier_identity,
            )
            return SchemaUpgradeReceipt(
                schema_version=UPGRADE_COMPLETION_SCHEMA,
                database_path=str(database),
                release_sha=release["release_sha"],
                preflight_receipt_path=str(preflight_path),
                preflight_receipt_digest=preflight_digest,
                completion_receipt_path=str(completion_path),
                completion_receipt_digest=_upgrade_digest(completion),
                pre_v4_legacy_content_digest=before["legacy_content_digest"],
                post_v4_legacy_content_digest=verified_v4["legacy_content_digest"],
                v3_backup_path=v3_backup.database_path,
                v4_backup_path=v4_backup.database_path,
                completed_at=completed_at,
            )
        except Exception as exc:
            if committed_v4:
                _ensure_upgrade_quarantine_barrier(barrier, barrier_payload)
                raise ExecutiveSchemaUpgradeError(
                    "v4 committed but completion failed; barrier remains for forward fix"
                ) from exc
            if before is None or barrier_identity is None or census is None:
                _ensure_upgrade_quarantine_barrier(barrier, barrier_payload)
                raise ExecutiveSchemaUpgradeError(
                    "precommit upgrade failed before exact rollback proof; barrier remains"
                ) from exc
            try:
                _upgrade_hook("after_precommit_rollback_before_guard")
                current = _upgrade_database_state(database, version=3)
                if not _rollback_reproduces_preflight(current, before):
                    raise ExecutiveSchemaUpgradeError(
                        "rolled-back v3 state differs from frozen preflight"
                    )
                if _prove_upgrade_release(release_sha) != release:
                    raise ExecutiveSchemaUpgradeError(
                        "tool release identity changed before rollback cleanup"
                    )
                if _upgrade_census(database, lock, barrier, lock_fd) != census:
                    raise RestoreSafetyError(
                        "writer census changed before rollback barrier release"
                    )
                if _marker_exists(marker):
                    raise RestoreSafetyError(
                        "Executive service marker appeared before rollback cleanup"
                    )
                _held_service_lock_identity(lock, lock_fd, lock_identity)
                _artifact_identity(
                    barrier,
                    expected_payload=barrier_payload,
                    expected=barrier_identity,
                )
                if preflight is not None and preflight_identity is not None:
                    _artifact_identity(
                        preflight_path,
                        expected_payload=preflight,
                        expected=preflight_identity,
                    )
                    _unlink_exact_upgrade_artifact(
                        preflight_path,
                        expected_payload=preflight,
                        expected=preflight_identity,
                    )
                _unlink_exact_upgrade_artifact(
                    barrier,
                    expected_payload=barrier_payload,
                    expected=barrier_identity,
                )
            except Exception as guard_exc:
                _ensure_upgrade_quarantine_barrier(barrier, barrier_payload)
                raise ExecutiveSchemaUpgradeError(
                    "v3 rollback did not reproduce preflight; barrier remains"
                ) from guard_exc
            raise ExecutiveSchemaUpgradeError(
                f"v3 migration rolled back without v4 commit: {type(exc).__name__}: {exc}"
            ) from exc


def upgrade_v4_to_v5(
    database_path: str | Path,
    backup_directory: str | Path,
    *,
    release_sha: str,
) -> SchemaUpgradeV4ToV5Receipt:
    """Perform the sole explicit, offline, forward-only exact-v4 -> v5 upgrade.

    The transition reuses the same offline custody chain as ``upgrade_v3_to_v4``
    (installed-release proof, canonical service flock and absent marker, the
    same quarantine barrier, stable writer census, quiesced WAL checkpoint,
    verified private source backup plus restore drill, immutable preflight and
    completion receipts, BEGIN EXCLUSIVE with revalidation, and exact
    post-commit proof) but remains a separate closed function: it accepts only
    an exact v4 source, executes only migration 5 (the finite-arm partial
    unique index), and never shares caller-supplied SQL or arbitrary versions.
    Preexisting duplicate ``COO_FINITE_DRIVE_ARMED`` rows make the index
    creation fail atomically; nothing is deduplicated.
    """

    release = _prove_upgrade_release(release_sha)
    candidate = Path(database_path).expanduser()
    _assert_private_regular_file(candidate, label="Executive exact-v4 database")
    database = candidate.resolve(strict=True)
    state_directory = database.parent
    marker = state_directory / DEFAULT_SERVICE_MARKER_NAME
    lock = state_directory / DEFAULT_SERVICE_LOCK_NAME
    barrier = state_directory / _UPGRADE_BARRIER_NAME
    preflight_path = state_directory / _UPGRADE_V4_TO_V5_PREFLIGHT_NAME
    completion_path = state_directory / _UPGRADE_V4_TO_V5_COMPLETION_NAME
    if any(os.path.lexists(path) for path in (barrier, preflight_path, completion_path)):
        raise ExecutiveSchemaUpgradeError(
            "v4-to-v5 upgrade barrier/receipt already exists; explicit operator "
            "reconciliation required before another attempt"
        )
    operation_id = uuid4().hex
    created_at = _upgrade_now()
    barrier_payload = {
        "schema_version": UPGRADE_BARRIER_SCHEMA,
        "operation_id": operation_id,
        "database_path": str(database),
        "tool_release_root": release["release_root"],
        "tool_release_tree_sha": release["release_tree_sha"],
        "tool_release_manifest_sha256": release["release_manifest_sha256"],
        "release_sha": release["release_sha"],
        "control_uid": os.geteuid(),
        "created_at": created_at,
    }
    before: dict[str, Any] | None = None
    preflight: dict[str, Any] | None = None
    barrier_identity: dict[str, Any] | None = None
    preflight_identity: dict[str, Any] | None = None
    census: dict[str, Any] | None = None
    committed_v5 = False
    with _offline_restore_lock(lock, marker, require_existing=True) as lock_fd:
        lock_identity = _held_service_lock_identity(lock, lock_fd)
        _write_private_json(barrier, barrier_payload)
        barrier_identity = _artifact_identity(
            barrier, expected_payload=barrier_payload
        )
        try:
            _upgrade_hook("barrier_persisted")
            _artifact_identity(
                barrier,
                expected_payload=barrier_payload,
                expected=barrier_identity,
            )
            if _marker_exists(marker):
                raise RestoreSafetyError("Executive service marker appeared before census")
            census = _upgrade_census(database, lock, barrier, lock_fd)
            _checkpoint_quiesced_wal(database)
            if _upgrade_census(database, lock, barrier, lock_fd) != census:
                raise RestoreSafetyError("writer census changed across WAL checkpoint")
            before = _upgrade_database_state(database, version=4)
            v4_backup = create_offline_backup(
                database, backup_directory, expected_schema_version=4
            )
            v4_drill = verify_restore_drill(
                v4_backup.database_path,
                v4_backup.manifest_path,
                expected_schema_version=4,
            )
            with _readonly_database(Path(v4_backup.database_path)) as connection:
                backup_full_v4 = full_v4_content_digest(connection)
            if (
                v4_backup.legacy_content_digest != before["legacy_content_digest"]
                or v4_drill.legacy_content_digest != before["legacy_content_digest"]
                or v4_backup.normalized_schema_digest
                != before["normalized_schema_digest"]
                or v4_drill.normalized_schema_digest
                != before["normalized_schema_digest"]
                or backup_full_v4 != before["full_v4_content_digest"]
            ):
                raise ExecutiveSchemaUpgradeError("v4 source/backup/drill proof differs")
            preflight = {
                "schema_version": UPGRADE_PREFLIGHT_SCHEMA,
                "operation_id": operation_id,
                "source_schema_version": 4,
                "target_schema_version": 5,
                "database": before["database"],
                "migration_vector": before["migration_vector"],
                "normalized_schema_digest": before["normalized_schema_digest"],
                "full_v4_content_digest": before["full_v4_content_digest"],
                "barrier_identity": barrier_identity,
                "v4_backup": {
                    "database_path": v4_backup.database_path,
                    "database_sha256": v4_backup.database_sha256,
                    "manifest_path": v4_backup.manifest_path,
                    "manifest_sha256": v4_backup.manifest_sha256,
                    "restore_drill_receipt": v4_drill.to_dict(),
                    "restore_drill_digest": _upgrade_digest(v4_drill.to_dict()),
                    "full_v4_content_digest": backup_full_v4,
                },
                "quiesce_writer_census": census,
                "quiesce_writer_census_digest": _upgrade_digest(census),
                "tool_release_root": release["release_root"],
                "tool_release_tree_sha": release["release_tree_sha"],
                "tool_release_manifest_sha256": release[
                    "release_manifest_sha256"
                ],
                "release_sha": release["release_sha"],
                "created_at": created_at,
            }
            _write_private_json(preflight_path, preflight)
            preflight_identity = _artifact_identity(
                preflight_path, expected_payload=preflight
            )
            preflight_digest = _upgrade_digest(preflight)
            _upgrade_hook("preflight_persisted")

            def revalidate_control_artifacts() -> None:
                if _marker_exists(marker):
                    raise RestoreSafetyError(
                        "Executive service marker appeared during schema upgrade"
                    )
                _held_service_lock_identity(lock, lock_fd, lock_identity)
                _artifact_identity(
                    barrier,
                    expected_payload=barrier_payload,
                    expected=barrier_identity,
                )
                _artifact_identity(
                    preflight_path,
                    expected_payload=preflight,
                    expected=preflight_identity,
                )
                if _prove_upgrade_release(release_sha) != release:
                    raise ExecutiveSchemaUpgradeError("tool release identity changed")
                _assert_upgrade_database_inode(database, before)

            def revalidate_v4_backup_proof() -> None:
                checked = verify_backup(
                    v4_backup.database_path,
                    v4_backup.manifest_path,
                    expected_schema_version=4,
                )
                checked_drill = verify_restore_drill(
                    v4_backup.database_path,
                    v4_backup.manifest_path,
                    expected_schema_version=4,
                )
                with _readonly_database(Path(v4_backup.database_path)) as connection:
                    checked_full_v4 = full_v4_content_digest(connection)
                if (
                    checked.database_sha256 != v4_backup.database_sha256
                    or checked.manifest_sha256 != v4_backup.manifest_sha256
                    or checked.normalized_schema_digest
                    != v4_backup.normalized_schema_digest
                    or checked.legacy_content_digest
                    != v4_backup.legacy_content_digest
                    or checked_full_v4 != backup_full_v4
                    or checked_drill.to_dict() != v4_drill.to_dict()
                    or _upgrade_digest(checked_drill.to_dict())
                    != preflight["v4_backup"]["restore_drill_digest"]
                ):
                    raise ExecutiveSchemaUpgradeError(
                        "v4 backup or restore-drill proof changed after preflight"
                    )

            revalidate_control_artifacts()
            revalidate_v4_backup_proof()
            if _upgrade_database_state(database, version=4) != before:
                raise ExecutiveSchemaUpgradeError("v4 source changed after preflight")
            if _upgrade_census(database, lock, barrier, lock_fd) != census:
                raise RestoreSafetyError("writer census changed before migration")

            connection = sqlite3.connect(database, isolation_level=None, timeout=5.0)
            connection.row_factory = sqlite3.Row
            try:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("BEGIN EXCLUSIVE")
                revalidate_control_artifacts()
                _verify_connection(connection, expected_schema_version=4)
                if full_v4_content_digest(
                    connection
                ) != before["full_v4_content_digest"]:
                    raise ExecutiveSchemaUpgradeError("in-transaction v4 content changed")
                _upgrade_hook("exclusive_v4_verified")
                revalidate_control_artifacts()
                version, name, statements = _MIGRATIONS[4]
                if version != 5:
                    raise ExecutiveSchemaUpgradeError("reviewed migration 5 is unavailable")
                for ordinal, statement in enumerate(statements, 1):
                    connection.execute(statement)
                    _upgrade_hook(f"after_m5_statement:{ordinal:02d}")
                    revalidate_control_artifacts()
                connection.execute(
                    """
                    INSERT INTO schema_migrations(version,name,checksum,applied_at_ms)
                    VALUES(?,?,?,?)
                    """,
                    (
                        version,
                        name,
                        _migration_checksum(statements),
                        int(datetime.now(UTC).timestamp() * 1000),
                    ),
                )
                _upgrade_hook("after_m5_receipt")
                revalidate_control_artifacts()
                _verify_connection(connection, expected_schema_version=5)
                if full_v4_content_digest(
                    connection
                ) != before["full_v4_content_digest"]:
                    raise ExecutiveSchemaUpgradeError("migration changed full v4 content")
                _upgrade_hook("before_v5_commit")
                revalidate_control_artifacts()
                _verify_connection(connection, expected_schema_version=5)
                if full_v4_content_digest(
                    connection
                ) != before["full_v4_content_digest"]:
                    raise ExecutiveSchemaUpgradeError("precommit full v4 content drifted")
                connection.commit()
                committed_v5 = True
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()

            _upgrade_hook("after_v5_commit_before_checkpoint")
            revalidate_control_artifacts()
            _checkpoint_quiesced_wal(database)
            _upgrade_hook("after_v5_checkpoint")
            revalidate_control_artifacts()
            verified_v5 = _upgrade_database_state(database, version=5)
            if verified_v5["legacy_content_digest"] != before["legacy_content_digest"]:
                raise ExecutiveSchemaUpgradeError("committed v5 legacy content differs")
            with _readonly_database(database) as connection:
                committed_full_v4 = full_v4_content_digest(connection)
            if committed_full_v4 != before["full_v4_content_digest"]:
                raise ExecutiveSchemaUpgradeError("committed v5 full v4 content differs")
            v5_backup = create_offline_backup(
                database, backup_directory, expected_schema_version=5
            )
            v5_drill = verify_restore_drill(
                v5_backup.database_path,
                v5_backup.manifest_path,
                expected_schema_version=5,
            )
            with _readonly_database(Path(v5_backup.database_path)) as connection:
                v5_backup_full_v4 = full_v4_content_digest(connection)
            if (
                v5_backup.legacy_content_digest != before["legacy_content_digest"]
                or v5_drill.legacy_content_digest != before["legacy_content_digest"]
                or v5_backup.normalized_schema_digest
                != verified_v5["normalized_schema_digest"]
                or v5_drill.normalized_schema_digest
                != verified_v5["normalized_schema_digest"]
                or v5_backup_full_v4 != before["full_v4_content_digest"]
            ):
                raise ExecutiveSchemaUpgradeError("v5 source/backup/drill proof differs")
            if _upgrade_census(database, lock, barrier, lock_fd) != census:
                raise RestoreSafetyError("writer census changed before completion")
            revalidate_control_artifacts()
            completed_at = _upgrade_now()
            completion = {
                "schema_version": UPGRADE_COMPLETION_SCHEMA,
                "operation_id": operation_id,
                "source_schema_version": 4,
                "target_schema_version": 5,
                "preflight_receipt_digest": preflight_digest,
                "authoritative_v5_database": verified_v5["database"],
                "authoritative_v5_schema_digest": verified_v5[
                    "normalized_schema_digest"
                ],
                "migration_vector": verified_v5["migration_vector"],
                "pre_full_v4_content_digest": before["full_v4_content_digest"],
                "post_full_v4_content_digest": committed_full_v4,
                "full_v4_content_equal": True,
                "pre_v4_legacy_content_digest": before["legacy_content_digest"],
                "post_v4_legacy_content_digest": verified_v5[
                    "legacy_content_digest"
                ],
                "legacy_content_equal": True,
                "v5_backup": {
                    "database_path": v5_backup.database_path,
                    "database_sha256": v5_backup.database_sha256,
                    "manifest_path": v5_backup.manifest_path,
                    "manifest_sha256": v5_backup.manifest_sha256,
                    "restore_drill_receipt": v5_drill.to_dict(),
                    "restore_drill_digest": _upgrade_digest(v5_drill.to_dict()),
                    "full_v4_content_digest": v5_backup_full_v4,
                },
                "quiesce_writer_census_digest": _upgrade_digest(census),
                "tool_release_root": release["release_root"],
                "tool_release_tree_sha": release["release_tree_sha"],
                "tool_release_manifest_sha256": release[
                    "release_manifest_sha256"
                ],
                "release_sha": release["release_sha"],
                "completed_at": completed_at,
            }
            _write_private_json(completion_path, completion)
            completion_identity = _artifact_identity(
                completion_path, expected_payload=completion
            )
            _upgrade_hook("completion_persisted")
            # The final adversarial seam is deliberately placed before the
            # complete authoritative/backup/drill/census proof.  Nothing after
            # this hook may escape revalidation before the barrier is removed.
            _upgrade_hook("before_barrier_unlink")
            revalidate_control_artifacts()
            _artifact_identity(
                completion_path,
                expected_payload=completion,
                expected=completion_identity,
            )
            final_v5 = _upgrade_database_state(database, version=5)
            final_v5_backup = verify_backup(
                v5_backup.database_path,
                v5_backup.manifest_path,
                expected_schema_version=5,
            )
            final_v5_drill = verify_restore_drill(
                v5_backup.database_path,
                v5_backup.manifest_path,
                expected_schema_version=5,
            )
            with _readonly_database(database) as connection:
                final_full_v4 = full_v4_content_digest(connection)
            if (
                final_v5 != verified_v5
                or final_full_v4 != before["full_v4_content_digest"]
                or final_v5_backup.database_sha256 != v5_backup.database_sha256
                or final_v5_backup.manifest_sha256 != v5_backup.manifest_sha256
                or final_v5_backup.normalized_schema_digest
                != v5_backup.normalized_schema_digest
                or final_v5_backup.legacy_content_digest
                != v5_backup.legacy_content_digest
                or final_v5_drill.to_dict() != v5_drill.to_dict()
                or _upgrade_digest(final_v5_drill.to_dict())
                != completion["v5_backup"]["restore_drill_digest"]
            ):
                raise ExecutiveSchemaUpgradeError(
                    "completion v5 source/backup/drill proof changed"
                )
            # The retained source backup stays in custody after the commit, so
            # it is revalidated beside the final v5 proof before release.
            revalidate_v4_backup_proof()
            if _upgrade_census(database, lock, barrier, lock_fd) != census:
                raise RestoreSafetyError("writer census changed before barrier release")
            revalidate_control_artifacts()
            _artifact_identity(
                completion_path,
                expected_payload=completion,
                expected=completion_identity,
            )
            _unlink_exact_upgrade_artifact(
                barrier,
                expected_payload=barrier_payload,
                expected=barrier_identity,
            )
            return SchemaUpgradeV4ToV5Receipt(
                schema_version=UPGRADE_COMPLETION_SCHEMA,
                database_path=str(database),
                database_identity=dict(verified_v5["database"]),
                release_sha=release["release_sha"],
                preflight_receipt_path=str(preflight_path),
                preflight_receipt_digest=preflight_digest,
                completion_receipt_path=str(completion_path),
                completion_receipt_digest=_upgrade_digest(completion),
                source_schema_version=4,
                target_schema_version=5,
                pre_full_v4_content_digest=before["full_v4_content_digest"],
                post_full_v4_content_digest=committed_full_v4,
                full_v4_content_equal=True,
                v4_backup_path=v4_backup.database_path,
                v4_backup_manifest_path=v4_backup.manifest_path,
                v5_backup_path=v5_backup.database_path,
                v5_backup_manifest_path=v5_backup.manifest_path,
                completed_at=completed_at,
            )
        except Exception as exc:
            if committed_v5:
                _ensure_upgrade_quarantine_barrier(barrier, barrier_payload)
                raise ExecutiveSchemaUpgradeError(
                    "v5 committed but completion failed; barrier remains for forward fix"
                ) from exc
            if before is None or barrier_identity is None or census is None:
                _ensure_upgrade_quarantine_barrier(barrier, barrier_payload)
                raise ExecutiveSchemaUpgradeError(
                    "precommit upgrade failed before exact rollback proof; barrier remains"
                ) from exc
            try:
                _upgrade_hook("after_precommit_rollback_before_guard")
                current = _upgrade_database_state(database, version=4)
                if not _rollback_reproduces_preflight(current, before):
                    raise ExecutiveSchemaUpgradeError(
                        "rolled-back v4 state differs from frozen preflight"
                    )
                if _prove_upgrade_release(release_sha) != release:
                    raise ExecutiveSchemaUpgradeError(
                        "tool release identity changed before rollback cleanup"
                    )
                if _upgrade_census(database, lock, barrier, lock_fd) != census:
                    raise RestoreSafetyError(
                        "writer census changed before rollback barrier release"
                    )
                if _marker_exists(marker):
                    raise RestoreSafetyError(
                        "Executive service marker appeared before rollback cleanup"
                    )
                _held_service_lock_identity(lock, lock_fd, lock_identity)
                _artifact_identity(
                    barrier,
                    expected_payload=barrier_payload,
                    expected=barrier_identity,
                )
                if preflight is not None and preflight_identity is not None:
                    _artifact_identity(
                        preflight_path,
                        expected_payload=preflight,
                        expected=preflight_identity,
                    )
                    _unlink_exact_upgrade_artifact(
                        preflight_path,
                        expected_payload=preflight,
                        expected=preflight_identity,
                    )
                _unlink_exact_upgrade_artifact(
                    barrier,
                    expected_payload=barrier_payload,
                    expected=barrier_identity,
                )
            except Exception as guard_exc:
                _ensure_upgrade_quarantine_barrier(barrier, barrier_payload)
                raise ExecutiveSchemaUpgradeError(
                    "v4 rollback did not reproduce preflight; barrier remains"
                ) from guard_exc
            raise ExecutiveSchemaUpgradeError(
                f"v4 migration rolled back without v5 commit: {type(exc).__name__}: {exc}"
            ) from exc



def _require_retained_backup_sidecar_absence(path: str | Path) -> None:
    database = Path(path)
    if any(os.path.lexists(_sidecar(database, suffix)) for suffix in _SIDECAR_SUFFIXES):
        raise ExecutiveSchemaUpgradeError("retained upgrade backup has a SQLite sidecar")


def _v5_migration_receipt_digest(connection: sqlite3.Connection) -> str:
    """Preserve migration 5's exact receipt, outside the full-v4 projection."""
    rows = connection.execute(
        "SELECT typeof(version),version,typeof(name),name,typeof(checksum),checksum,"
        "typeof(applied_at_ms),applied_at_ms FROM schema_migrations WHERE version=5"
    ).fetchall()
    expected = _expected_migrations(5)[-1]
    if (len(rows) != 1 or tuple(rows[0][:6]) != (
            "integer", 5, "text", expected.name, "text", expected.checksum)
            or rows[0][6] != "integer" or type(rows[0][7]) is not int):
        raise BackupVerificationError("migration 5 receipt identity/storage class is invalid")
    return _upgrade_digest(list(rows[0]))


def _upgrade_v5_retained_state(database: Path, *, version: int) -> dict[str, Any]:
    state = _upgrade_database_state(database, version=version)
    with _readonly_database(database) as connection:
        state["v5_migration_receipt_digest"] = _v5_migration_receipt_digest(connection)
    return state


# Closed, fixed-original-operation recovery wire. Ordinary upgrades do not
# consume these receipts and retain their existing barrier-refusal behavior.
PRE_CENSUS_QUALIFICATION_SCHEMA = "mastermind.executive_schema_upgrade_pre_census_qualification/v1"
PRE_CENSUS_CONTINUATION_SCHEMA = "mastermind.executive_schema_upgrade_pre_census_continuation/v1"
PRE_CENSUS_PREFLIGHT_SCHEMA = "mastermind.executive_schema_upgrade_pre_census_preflight/v1"
PRE_CENSUS_CENSUS_SCHEMA = "mastermind.executive_schema_upgrade_quiesce/pre_census_recovery_v1"
PRE_CENSUS_INSPECTION_SCHEMA = "mastermind.executive_schema_upgrade_pre_census_inspection/v1"
PRE_CENSUS_QUALIFICATION_NAME = "executive-schema-upgrade.v5-to-v6.pre-census-qualification.json"
PRE_CENSUS_CONTINUATION_NAME = "executive-schema-upgrade.v5-to-v6.pre-census-continuation.json"
SPENT_PRE_CENSUS_CTIME_RECONCILIATION_SCHEMA = "mastermind.executive_schema_upgrade_spent_pre_census_ctime_reconciliation/v1"
SPENT_PRE_CENSUS_CTIME_CONTINUATION_SCHEMA = "mastermind.executive_schema_upgrade_spent_pre_census_ctime_continuation/v1"
SPENT_PRE_CENSUS_CTIME_PREFLIGHT_SCHEMA = "mastermind.executive_schema_upgrade_spent_pre_census_ctime_preflight/v1"
SPENT_PRE_CENSUS_CTIME_RECONCILIATION_NAME = "executive-schema-upgrade.v5-to-v6.spent-pre-census-ctime-reconciliation.json"
SPENT_PRE_CENSUS_CTIME_CONTINUATION_NAME = "executive-schema-upgrade.v5-to-v6.spent-pre-census-ctime-continuation.json"
_PRE_CENSUS_DATABASE = Path("/private/var/db/mastermind-executive/control/db/data/control_plane/executive.sqlite3")
_PRE_CENSUS_RELEASES = Path("/Library/Application Support/MastermindExecutive/releases")
_PRE_CENSUS_LIMIT = 64 * 1024
_PRE_CENSUS_BARRIER_KEYS = frozenset({
    "schema_version", "operation_id", "database_path", "tool_release_root",
    "tool_release_tree_sha", "tool_release_manifest_sha256", "release_sha",
    "control_uid", "created_at",
})
_PRE_CENSUS_QUALIFICATION_KEYS = frozenset({
    "schema_version", "operation_id", "original_barrier", "original_tool",
    "recovery_tool", "database", "normalized_schema_digest",
    "full_v5_content_digest", "migration_vector", "selected_source",
    "source_control_config", "host", "created_at", "backup_inventory_sha256",
})
_PRE_CENSUS_IDENTITY_KEYS = frozenset({"path", "device", "inode", "size", "sha256", "payload_digest"})
_PRE_CENSUS_ORIGIN_KEYS = frozenset({
    "path", "device", "inode", "uid", "gid", "mode", "nlink", "size",
    "mtime_ns", "ctime_ns", "sha256",
})


def _pre_census_closed(value: Any, keys: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ExecutiveSchemaUpgradeError(f"pre-census {label} has an unsupported shape")
    return dict(value)


def _pre_census_hash(value: Any, *, length: int = 64) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value) is None:
        raise ExecutiveSchemaUpgradeError("pre-census digest or identity is malformed")
    return value


def _pre_census_time(value: Any) -> str:
    if not isinstance(value, str):
        raise ExecutiveSchemaUpgradeError("pre-census timestamp is malformed")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExecutiveSchemaUpgradeError("pre-census timestamp is malformed") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ExecutiveSchemaUpgradeError("pre-census timestamp is not explicit UTC")
    return value


def _pre_census_control_identity() -> tuple[int, int]:
    import pwd
    import grp
    from ops.executive_os.autonomy_control import CONTROL_USER, CONTROL_GROUP
    user, group = pwd.getpwnam(CONTROL_USER), grp.getgrnam(CONTROL_GROUP)
    if (user.pw_name != CONTROL_USER or group.gr_name != CONTROL_GROUP
            or type(user.pw_uid) is not int or user.pw_uid <= 0
            or type(group.gr_gid) is not int or group.gr_gid <= 0
            or user.pw_gid != group.gr_gid):
        raise ExecutiveSchemaUpgradeError("pre-census fixed Control identity is ambiguous")
    return user.pw_uid, group.gr_gid


def _pre_census_stat(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _pre_census_ancestors(path: Path, uid: int, gid: int) -> tuple:
    """Known-ancestor metadata only: never directory READ, enumeration or ACL open."""
    if path.parent != _PRE_CENSUS_DATABASE.parent:
        raise ExecutiveSchemaUpgradeError("pre-census leaf is outside the fixed namespace")
    top = _PRE_CENSUS_DATABASE.parents[4]
    result = []
    for ancestor in reversed(path.parents):
        info = os.lstat(ancestor)
        if ancestor == top:
            owner, group, mode = 0, 0, 0o711
        elif top in ancestor.parents:
            owner, group, mode = uid, gid, 0o700
        else:
            owner, group, mode = 0, 0, 0o755
        if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                or info.st_uid != owner or info.st_gid != group
                or stat.S_IMODE(info.st_mode) != mode):
            raise ExecutiveSchemaUpgradeError("pre-census ancestor metadata is unqualified")
        result.append((str(ancestor), info.st_dev, info.st_ino, info.st_uid,
                       info.st_gid, info.st_mode))
    return tuple(result)


def _pre_census_leaf(path: Path, fd: int, *, uid: int, gid: int, mode: int) -> os.stat_result:
    from control_plane.fs_security import has_macos_acl
    info, named = os.fstat(fd), os.lstat(path)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid or info.st_gid != gid
            or stat.S_IMODE(info.st_mode) != mode or info.st_nlink != 1
            or not 0 < info.st_size <= _PRE_CENSUS_LIMIT
            or _pre_census_stat(named) != _pre_census_stat(info)
            or has_macos_acl(path, descriptor=fd, expected_identity=info)):
        raise ExecutiveSchemaUpgradeError("pre-census leaf custody is unqualified")
    return info


def _pre_census_read(path: Path, fd: int, *, uid: int, gid: int, mode: int) -> tuple[bytes, os.stat_result]:
    before = _pre_census_leaf(path, fd, uid=uid, gid=gid, mode=mode)
    chunks, total = [], 0
    while True:
        chunk = os.read(fd, min(64 * 1024, _PRE_CENSUS_LIMIT + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > _PRE_CENSUS_LIMIT:
            raise ExecutiveSchemaUpgradeError("pre-census artifact exceeds its bound")
    raw = b"".join(chunks)
    after = _pre_census_leaf(path, fd, uid=uid, gid=gid, mode=mode)
    if len(raw) != before.st_size or _pre_census_stat(after) != _pre_census_stat(before):
        raise ExecutiveSchemaUpgradeError("pre-census leaf changed during read")
    return raw, after


def _pre_census_artifact_identity(path: Path, *, uid: int, gid: int, mode: int) -> dict[str, Any]:
    """Descriptor-qualified finite receipt identity; never pathname-hash fallback."""
    path = Path(path)
    ancestors = _pre_census_ancestors(path, *_pre_census_control_identity())
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0))
    try:
        raw, info = _pre_census_read(path, fd, uid=uid, gid=gid, mode=mode)
        value = _strict_json(raw)
        if not isinstance(value, dict) or _upgrade_receipt_bytes(value) != raw:
            raise ExecutiveSchemaUpgradeError("pre-census receipt is not canonical JSON")
        result = {"path": str(path), "device": info.st_dev, "inode": info.st_ino,
                  "size": info.st_size, "sha256": hashlib.sha256(raw).hexdigest(),
                  "payload_digest": _upgrade_digest(value)}
        if ancestors != _pre_census_ancestors(path, *_pre_census_control_identity()):
            raise ExecutiveSchemaUpgradeError("pre-census artifact ancestry changed")
        _pre_census_leaf(path, fd, uid=uid, gid=gid, mode=mode)
        return result
    finally:
        os.close(fd)


def _pre_census_tool(value: Any) -> dict[str, str]:
    tool = _pre_census_closed(value, frozenset({"root", "sha", "tree_sha", "manifest_sha256"}), "tool")
    _pre_census_hash(tool["sha"], length=40)
    _pre_census_hash(tool["tree_sha"], length=40)
    _pre_census_hash(tool["manifest_sha256"])
    if tool["root"] != str(_PRE_CENSUS_RELEASES / tool["sha"]):
        raise ExecutiveSchemaUpgradeError("pre-census tool root is not the fixed sealed release")
    return tool


def _validate_pre_census_barrier(value: Any, uid: int) -> dict[str, Any]:
    payload = _pre_census_closed(value, _PRE_CENSUS_BARRIER_KEYS, "original barrier")
    if (payload["schema_version"] != UPGRADE_BARRIER_SCHEMA
            or payload["database_path"] != str(_PRE_CENSUS_DATABASE)
            or type(payload["control_uid"]) is not int or payload["control_uid"] != uid):
        raise ExecutiveSchemaUpgradeError("pre-census original barrier binding differs")
    _pre_census_hash(payload["operation_id"], length=32)
    _pre_census_time(payload["created_at"])
    _pre_census_tool({"root": payload["tool_release_root"], "sha": payload["release_sha"],
                      "tree_sha": payload["tool_release_tree_sha"],
                      "manifest_sha256": payload["tool_release_manifest_sha256"]})
    return payload


class _PreCensusBarrierObservation:
    """Held leaf plus metadata-bracketed ancestry, not an ancestor-FD lock."""
    def __init__(self):
        self.uid, self.gid = _pre_census_control_identity()
        self.path = _PRE_CENSUS_DATABASE.parent / _UPGRADE_BARRIER_NAME
        self.ancestors = _pre_census_ancestors(self.path, self.uid, self.gid)
        self.fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0))
        try:
            self.raw, info = _pre_census_read(self.path, self.fd, uid=self.uid, gid=self.gid, mode=0o600)
            self.initial = _pre_census_stat(info)
            self.payload = _validate_pre_census_barrier(_strict_json(self.raw), self.uid)
            if self.raw != _upgrade_receipt_bytes(self.payload):
                raise ExecutiveSchemaUpgradeError("pre-census original barrier is not canonical")
            self.identity = {"path": str(self.path), "device": info.st_dev, "inode": info.st_ino,
                             "size": info.st_size, "sha256": hashlib.sha256(self.raw).hexdigest(),
                             "payload_digest": _upgrade_digest(self.payload)}
            self.check()
        except BaseException:
            os.close(self.fd)
            self.fd = -1
            raise

    def check(self) -> None:
        info = _pre_census_leaf(self.path, self.fd, uid=self.uid, gid=self.gid, mode=0o600)
        if (_pre_census_stat(info) != self.initial
                or self.ancestors != _pre_census_ancestors(self.path, self.uid, self.gid)):
            raise ExecutiveSchemaUpgradeError("pre-census original barrier identity changed")
        if os.geteuid() == self.uid:
            actual = _artifact_identity(self.path, expected_payload=self.payload, expected=self.identity)
        else:
            actual = _pre_census_artifact_identity(self.path, uid=self.uid, gid=self.gid, mode=0o600)
        if actual != self.identity:
            raise ExecutiveSchemaUpgradeError("pre-census original barrier bytes changed")
        if (_pre_census_stat(_pre_census_leaf(self.path, self.fd, uid=self.uid, gid=self.gid, mode=0o600)) != self.initial
                or self.ancestors != _pre_census_ancestors(self.path, self.uid, self.gid)):
            raise ExecutiveSchemaUpgradeError("pre-census original barrier changed at return")

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


@contextmanager
def _open_pre_census_barrier_for_root_issuer(database_path: Path) -> Iterator[_PreCensusBarrierObservation]:
    if os.geteuid() != 0 or Path(database_path) != _PRE_CENSUS_DATABASE:
        raise ExecutiveSchemaUpgradeError("pre-census issuer requires Root at the fixed database")
    value = _PreCensusBarrierObservation()
    try:
        yield value
        value.check()
    finally:
        value.close()


def inspect_v5_to_v6_pre_census_barrier() -> dict[str, Any]:
    """Read-only fixed-leaf DATA; no database, service, lock or migration access."""
    uid, gid = _pre_census_control_identity()
    if os.geteuid() != uid or os.getegid() != gid:
        raise ExecutiveSchemaUpgradeError("pre-census inspection requires the fixed Control caller")
    value = _PreCensusBarrierObservation()
    try:
        result = {"schema_version": PRE_CENSUS_INSPECTION_SCHEMA,
                  "original_barrier": {"payload": dict(value.payload), "identity": dict(value.identity)},
                  "custody": {"uid": uid, "gid": gid, "mode": 0o600, "nlink": 1}}
        value.check()
        return result
    finally:
        value.close()


def _validate_pre_census_qualification(value: Any) -> dict[str, Any]:
    """Pure closed-wire DATA validation; this is not Root authority or a reader."""
    payload = _pre_census_closed(value, _PRE_CENSUS_QUALIFICATION_KEYS, "qualification")
    if payload["schema_version"] != PRE_CENSUS_QUALIFICATION_SCHEMA:
        raise ExecutiveSchemaUpgradeError("pre-census qualification schema differs")
    host = _pre_census_closed(payload["host"], frozenset({"runtime_root", "backup_root", "control_uid", "control_gid"}), "host")
    for name in ("control_uid", "control_gid"):
        if type(host[name]) is not int or host[name] <= 0:
            raise ExecutiveSchemaUpgradeError("pre-census qualification principal is malformed")
    if host["runtime_root"] != str(_PRE_CENSUS_DATABASE.parents[2]) or host["backup_root"] != str(_PRE_CENSUS_DATABASE.parents[3] / "backups"):
        raise ExecutiveSchemaUpgradeError("pre-census qualification roots differ")
    original = _pre_census_closed(payload["original_barrier"], frozenset({"payload", "identity"}), "barrier observation")
    barrier = _validate_pre_census_barrier(original["payload"], host["control_uid"])
    identity = _pre_census_closed(original["identity"], _PRE_CENSUS_IDENTITY_KEYS, "barrier identity")
    raw = _upgrade_receipt_bytes(barrier)
    if (identity["path"] != str(_PRE_CENSUS_DATABASE.parent / _UPGRADE_BARRIER_NAME)
            or identity["size"] != len(raw) or identity["sha256"] != hashlib.sha256(raw).hexdigest()
            or identity["payload_digest"] != _upgrade_digest(barrier)
            or payload["operation_id"] != barrier["operation_id"]):
        raise ExecutiveSchemaUpgradeError("pre-census qualification original barrier differs")
    for name in ("device", "inode"):
        if type(identity[name]) is not int or identity[name] < 0:
            raise ExecutiveSchemaUpgradeError("pre-census barrier identity is malformed")
    old = _pre_census_tool(payload["original_tool"])
    if old != {"root": barrier["tool_release_root"], "sha": barrier["release_sha"], "tree_sha": barrier["tool_release_tree_sha"], "manifest_sha256": barrier["tool_release_manifest_sha256"]}:
        raise ExecutiveSchemaUpgradeError("pre-census qualification original tool differs")
    new = _pre_census_tool(payload["recovery_tool"])
    if old["sha"] == new["sha"]:
        raise ExecutiveSchemaUpgradeError("pre-census corrected executor must be a distinct sealed release")
    database = _pre_census_closed(payload["database"], _PRE_CENSUS_ORIGIN_KEYS, "database origin")
    if (database["path"] != str(_PRE_CENSUS_DATABASE) or database["uid"] != host["control_uid"]
            or database["gid"] != host["control_gid"] or database["mode"] != 0o600 or database["nlink"] != 1):
        raise ExecutiveSchemaUpgradeError("pre-census qualification database custody differs")
    for name in _PRE_CENSUS_ORIGIN_KEYS - {"path", "sha256"}:
        if type(database[name]) is not int or database[name] < 0:
            raise ExecutiveSchemaUpgradeError("pre-census database identity is malformed")
    for name in ("normalized_schema_digest", "full_v5_content_digest", "backup_inventory_sha256"):
        _pre_census_hash(payload[name])
    _pre_census_hash(database["sha256"])
    if not isinstance(payload["migration_vector"], list) or len(payload["migration_vector"]) != 5:
        raise ExecutiveSchemaUpgradeError("pre-census qualification migration vector is malformed")
    for version, item in enumerate(payload["migration_vector"], start=1):
        record = _pre_census_closed(item, frozenset({"version", "name", "checksum"}), "migration")
        if (type(record["version"]) is not int or record["version"] != version
                or not isinstance(record["name"], str) or not record["name"]):
            raise ExecutiveSchemaUpgradeError("pre-census qualification migration vector differs")
        _pre_census_hash(record["checksum"])
    selected = _pre_census_closed(payload["selected_source"], frozenset({"sha", "descriptor_raw_sha256", "descriptor_sha256", "source_backup_sha256", "baseline_sha256", "inventory_sha256", "prior_canary_sha256"}), "selected source")
    for name, item in selected.items():
        _pre_census_hash(item, length=40 if name == "sha" else 64)
    config = _pre_census_closed(payload["source_control_config"], frozenset({"path", "sha256"}), "source config")
    if config["path"] != str(_PRE_CENSUS_RELEASES.parent / "config" / "control.json"):
        raise ExecutiveSchemaUpgradeError("pre-census qualification source config differs")
    _pre_census_hash(config["sha256"])
    _pre_census_time(payload["created_at"])
    return json.loads(json.dumps(payload))


def _pre_census_argument(value: str | Path, fixed: Path) -> Path:
    candidate = Path(value)
    if candidate == fixed:
        return fixed
    if str(fixed).startswith("/private/var/") and candidate == Path(str(fixed)[8:]):
        alias = os.lstat("/var")
        if (not stat.S_ISLNK(alias.st_mode) or alias.st_uid != 0 or alias.st_gid != 0
                or os.readlink("/var") not in ("private/var", "/private/var")):
            raise ExecutiveSchemaUpgradeError("pre-census fixed /var alias is unqualified")
        return fixed
    raise ExecutiveSchemaUpgradeError("pre-census argument is outside the fixed namespace")


def _pre_census_alias_identity() -> tuple | None:
    """Only the production Darwin /var alias, never arbitrary resolution."""
    if not str(_PRE_CENSUS_DATABASE).startswith("/private/var/"):
        return None
    info = os.lstat("/var")
    target = os.readlink("/var")
    if (not stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_gid != 0
            or target not in ("private/var", "/private/var")):
        raise ExecutiveSchemaUpgradeError("pre-census fixed system alias is unqualified")
    return (_pre_census_stat(info), target)


def _pre_census_release_record(release: Mapping[str, str]) -> dict[str, str]:
    return {"root": release["release_root"], "sha": release["release_sha"],
            "tree_sha": release["release_tree_sha"],
            "manifest_sha256": release["release_manifest_sha256"]}


def _pre_census_prove_original_tool(tool: Mapping[str, str]) -> None:
    from ops.executive_os import autonomy_control, release_manifest
    tool = _pre_census_tool(tool)
    actual = dict(release_manifest.verify(Path(tool["root"]), tool["sha"], tool["tree_sha"]))
    actual["manifest_sha256"] = hashlib.sha256(autonomy_control._release_manifest_bytes(tool["sha"])).hexdigest()
    if (actual.get("commit_sha") != tool["sha"] or actual.get("tree_sha") != tool["tree_sha"]
            or actual.get("manifest_sha256") != tool["manifest_sha256"]):
        raise ExecutiveSchemaUpgradeError("pre-census original sealed tool proof differs")


class _PreCensusReceiptObservation:
    def __init__(self, path: Path, *, uid: int, gid: int, mode: int):
        self.path, self.uid, self.gid, self.mode = path, uid, gid, mode
        control_uid, control_gid = _pre_census_control_identity()
        self.ancestors = _pre_census_ancestors(path, control_uid, control_gid)
        self.fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0))
        try:
            self.raw, info = _pre_census_read(path, self.fd, uid=uid, gid=gid, mode=mode)
            self.initial = _pre_census_stat(info)
            self.payload = _strict_json(self.raw)
            if not isinstance(self.payload, dict) or _upgrade_receipt_bytes(self.payload) != self.raw:
                raise ExecutiveSchemaUpgradeError("pre-census receipt is not closed canonical data")
            self.identity = {"path": str(path), "device": info.st_dev, "inode": info.st_ino,
                             "size": info.st_size, "sha256": hashlib.sha256(self.raw).hexdigest(),
                             "payload_digest": _upgrade_digest(self.payload)}
            self.check()
        except BaseException:
            os.close(self.fd)
            self.fd = -1
            raise

    def check(self) -> None:
        info = _pre_census_leaf(self.path, self.fd, uid=self.uid, gid=self.gid, mode=self.mode)
        if (_pre_census_stat(info) != self.initial
                or self.ancestors != _pre_census_ancestors(self.path, *_pre_census_control_identity())
                or _pre_census_artifact_identity(self.path, uid=self.uid, gid=self.gid, mode=self.mode) != self.identity):
            raise ExecutiveSchemaUpgradeError("pre-census authority receipt changed while held")

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


def _pre_census_database_metadata(path: Path, fd: int, uid: int, gid: int) -> os.stat_result:
    from control_plane.fs_security import has_macos_acl
    info, named = os.fstat(fd), os.lstat(path)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid or info.st_gid != gid
            or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600
            or _pre_census_stat(info) != _pre_census_stat(named)
            or has_macos_acl(path, descriptor=fd, expected_identity=info)):
        raise ExecutiveSchemaUpgradeError("pre-census authoritative database custody differs")
    return info


def _pre_census_database_origin(path: Path, fd: int, uid: int, gid: int) -> dict[str, Any]:
    info = _pre_census_database_metadata(path, fd, uid, gid)
    digest, offset = hashlib.sha256(), 0
    while True:
        chunk = os.pread(fd, min(64 * 1024, info.st_size + 1 - offset), offset)
        if not chunk:
            break
        offset += len(chunk)
        if offset > info.st_size:
            raise ExecutiveSchemaUpgradeError("pre-census database grew during qualification")
        digest.update(chunk)
    after = _pre_census_database_metadata(path, fd, uid, gid)
    if offset != info.st_size or _pre_census_stat(info) != _pre_census_stat(after):
        raise ExecutiveSchemaUpgradeError("pre-census database changed during qualification")
    return {"path": str(path), "device": info.st_dev, "inode": info.st_ino,
            "uid": info.st_uid, "gid": info.st_gid, "mode": stat.S_IMODE(info.st_mode),
            "nlink": info.st_nlink, "size": info.st_size,
            "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns,
            "sha256": digest.hexdigest()}


def _pre_census_backup_inventory(backup_root: Path) -> dict[str, Any]:
    from ops.executive_os.acceptance_maintenance import inventory
    expected = _PRE_CENSUS_DATABASE.parents[3] / "backups"
    if backup_root != expected:
        raise ExecutiveSchemaUpgradeError("pre-census backup root is not fixed")
    return inventory([backup_root])


def _spent_receipt_identity(value: Any, payload: Mapping[str, Any], name: str) -> dict[str, Any]:
    identity = _pre_census_closed(value, _PRE_CENSUS_IDENTITY_KEYS, "spent receipt identity")
    raw = _upgrade_receipt_bytes(payload)
    if (identity["path"] != str(_PRE_CENSUS_DATABASE.parent / name)
            or identity["size"] != len(raw) or identity["sha256"] != hashlib.sha256(raw).hexdigest()
            or identity["payload_digest"] != _upgrade_digest(payload)):
        raise ExecutiveSchemaUpgradeError("spent pre-census receipt identity differs")
    for key in ("device", "inode", "size"):
        if type(identity[key]) is not int or identity[key] < 0:
            raise ExecutiveSchemaUpgradeError("spent pre-census receipt metadata is malformed")
    return identity


def _validate_spent_pre_census_sources(*, barrier_payload: Any, barrier_identity: Any,
        qualification_payload: Any, qualification_identity: Any,
        spent_continuation_payload: Any, spent_continuation_identity: Any) -> dict[str, Any]:
    q = _validate_pre_census_qualification(qualification_payload)
    if q["original_barrier"] != {"payload": barrier_payload, "identity": barrier_identity}:
        raise ExecutiveSchemaUpgradeError("spent pre-census original barrier differs")
    qi = _spent_receipt_identity(qualification_identity, q, PRE_CENSUS_QUALIFICATION_NAME)
    i = _pre_census_closed(spent_continuation_payload, frozenset({"schema_version", "operation_id",
        "original_barrier_identity", "qualification_identity", "recovery_tool", "created_at"}), "spent intent")
    expected = {"schema_version": PRE_CENSUS_CONTINUATION_SCHEMA, "operation_id": q["operation_id"],
        "original_barrier_identity": barrier_identity, "qualification_identity": qi,
        "recovery_tool": q["recovery_tool"], "created_at": i["created_at"]}
    _pre_census_time(i["created_at"])
    if i != expected:
        raise ExecutiveSchemaUpgradeError("spent pre-census immutable intent differs")
    _spent_receipt_identity(spent_continuation_identity, i, PRE_CENSUS_CONTINUATION_NAME)
    return q


def _validate_spent_pre_census_ctime_origin(original: Any, current: Any) -> dict[str, Any]:
    """Pure DATA: a different ctime epoch permits no other origin or byte change."""
    old = _pre_census_closed(original, _PRE_CENSUS_ORIGIN_KEYS, "original database origin")
    new = _pre_census_closed(current, _PRE_CENSUS_ORIGIN_KEYS, "current database origin")
    for record in (old, new):
        for key in _PRE_CENSUS_ORIGIN_KEYS - {"path", "sha256"}:
            if type(record[key]) is not int or record[key] < 0:
                raise ExecutiveSchemaUpgradeError("spent pre-census database metadata is malformed")
        if record["path"] != str(_PRE_CENSUS_DATABASE):
            raise ExecutiveSchemaUpgradeError("spent pre-census database path differs")
        _pre_census_hash(record["sha256"])
    if (old["ctime_ns"] == new["ctime_ns"]
            or any(old[key] != new[key] for key in _PRE_CENSUS_ORIGIN_KEYS - {"ctime_ns"})):
        raise ExecutiveSchemaUpgradeError("spent pre-census requires exact bytes and custody except new ctime")
    return json.loads(json.dumps(new))


def _validate_spent_pre_census_ctime_reconciliation(value: Any, *, barrier_payload: Any,
        barrier_identity: Any, qualification_payload: Any, qualification_identity: Any,
        spent_continuation_payload: Any, spent_continuation_identity: Any) -> dict[str, Any]:
    q = _validate_spent_pre_census_sources(barrier_payload=barrier_payload,
        barrier_identity=barrier_identity, qualification_payload=qualification_payload,
        qualification_identity=qualification_identity, spent_continuation_payload=spent_continuation_payload,
        spent_continuation_identity=spent_continuation_identity)
    value = _pre_census_closed(value, frozenset({"schema_version", "operation_id",
        "original_barrier_identity", "qualification_identity", "spent_continuation_identity",
        "recovery_tool", "database", "created_at"}), "ctime reconciliation")
    if (value["schema_version"] != SPENT_PRE_CENSUS_CTIME_RECONCILIATION_SCHEMA
            or value["operation_id"] != q["operation_id"]
            or value["original_barrier_identity"] != barrier_identity
            or value["qualification_identity"] != qualification_identity
            or value["spent_continuation_identity"] != spent_continuation_identity):
        raise ExecutiveSchemaUpgradeError("spent pre-census reconciliation links differ")
    tool = _pre_census_tool(value["recovery_tool"])
    if tool["sha"] in {q["original_tool"]["sha"], q["recovery_tool"]["sha"]}:
        raise ExecutiveSchemaUpgradeError("spent pre-census requires an honestly distinct executor")
    _validate_spent_pre_census_ctime_origin(q["database"], value["database"])
    _pre_census_time(value["created_at"])
    return json.loads(json.dumps(value))


class _SpentPreCensusObservation:
    """Held immutable old barrier/Q/I DATA, never proof that effects may resume."""
    def __init__(self):
        self.stack = ExitStack()
        try:
            uid, gid = _pre_census_control_identity()
            self.alias_identity = _pre_census_alias_identity()
            self.barrier = _PreCensusBarrierObservation()
            self.stack.callback(self.barrier.close)
            self.qualification = _PreCensusReceiptObservation(
                _PRE_CENSUS_DATABASE.parent / PRE_CENSUS_QUALIFICATION_NAME, uid=0, gid=gid, mode=0o440)
            self.stack.callback(self.qualification.close)
            self.spent_continuation = _PreCensusReceiptObservation(
                _PRE_CENSUS_DATABASE.parent / PRE_CENSUS_CONTINUATION_NAME, uid=uid, gid=gid, mode=0o600)
            self.stack.callback(self.spent_continuation.close)
            self.check()
        except BaseException:
            self.stack.close()
            raise

    def source_arguments(self) -> dict[str, Any]:
        return {"barrier_payload": self.barrier.payload, "barrier_identity": self.barrier.identity,
            "qualification_payload": self.qualification.payload, "qualification_identity": self.qualification.identity,
            "spent_continuation_payload": self.spent_continuation.payload,
            "spent_continuation_identity": self.spent_continuation.identity}

    def check(self) -> None:
        if _pre_census_alias_identity() != self.alias_identity:
            raise ExecutiveSchemaUpgradeError("spent pre-census fixed alias changed")
        for obs in (self.barrier, self.qualification, self.spent_continuation):
            obs.check()
        q = _validate_spent_pre_census_sources(**self.source_arguments())
        _pre_census_prove_original_tool(q["original_tool"])
        _pre_census_prove_original_tool(q["recovery_tool"])

    def close(self) -> None:
        self.stack.close()

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()


@contextmanager
def _open_spent_pre_census_for_root_issuer(database_path: str | Path) -> Iterator[_SpentPreCensusObservation]:
    if os.geteuid() != 0:
        raise ExecutiveSchemaUpgradeError("spent pre-census issuer requires actual Root")
    _pre_census_argument(database_path, _PRE_CENSUS_DATABASE)
    with _SpentPreCensusObservation() as observation:
        yield observation
        observation.check()


class _PreCensusContinuation:
    """Internally qualified, one-use Control operation, never a caller bypass DTO."""
    def __init__(self, database: Path, backup_root: Path, release_sha: str,
                 operation_id: str, barrier_sha256: str, lock_fd: int):
        from ops.executive_os.acceptance_maintenance import _RootConfig, require_disarmed
        self.stack = ExitStack()
        self.intent = None
        self.phase = "SOURCE"
        self.normal_artifacts: set[str] = set()
        self.connection = None
        self.journal_names: set[str] = set()
        self.sidecar_fds: dict[str, tuple[int, int, int]] = {}
        self.stack.callback(self._close_transaction_sidecars)
        self.alias_identity = _pre_census_alias_identity()
        self.database, self.backup_root, self.release_sha = database, backup_root, release_sha
        self.lock_fd = lock_fd
        self.lock = database.parent / DEFAULT_SERVICE_LOCK_NAME
        self.marker = database.parent / DEFAULT_SERVICE_MARKER_NAME
        self.intent_path = database.parent / PRE_CENSUS_CONTINUATION_NAME
        try:
            self.uid, self.gid = _pre_census_control_identity()
            if os.geteuid() != self.uid or os.getegid() != self.gid:
                raise ExecutiveSchemaUpgradeError("pre-census continuation requires fixed Control caller")
            if os.path.lexists(self.intent_path):
                raise ExecutiveSchemaUpgradeError("pre-census intent already exists; execution cannot be replayed")
            self.lock_identity = _held_service_lock_identity(self.lock, lock_fd)
            if os.fstat(lock_fd).st_gid != self.gid:
                raise ExecutiveSchemaUpgradeError("pre-census canonical lock group differs")
            self.barrier = _PreCensusBarrierObservation()
            self.stack.callback(self.barrier.close)
            if self.barrier.payload["operation_id"] != operation_id or self.barrier.identity["sha256"] != barrier_sha256:
                raise ExecutiveSchemaUpgradeError("pre-census original operation CAS differs")
            self.qualification = _PreCensusReceiptObservation(
                database.parent / PRE_CENSUS_QUALIFICATION_NAME, uid=0, gid=self.gid, mode=0o440)
            self.stack.callback(self.qualification.close)
            self.payload = _validate_pre_census_qualification(self.qualification.payload)
            if (self.payload["original_barrier"] != {"payload": self.barrier.payload, "identity": self.barrier.identity}
                    or self.payload["host"]["control_uid"] != self.uid
                    or self.payload["host"]["control_gid"] != self.gid
                    or self.payload["recovery_tool"] != _pre_census_release_record(_prove_upgrade_release(release_sha))):
                raise ExecutiveSchemaUpgradeError("pre-census Root qualification does not bind this operation")
            self.config = self.stack.enter_context(_RootConfig())
            require_disarmed(self.config.value)
            if (str(self.config.path) != self.payload["source_control_config"]["path"]
                    or hashlib.sha256(self.config.raw).hexdigest() != self.payload["source_control_config"]["sha256"]
                    or self.config.value.get("proof_base_sha") != self.payload["selected_source"]["sha"]
                    or _pre_census_argument(self.config.value["runtime_root"], database.parents[2]) != database.parents[2]
                    or _pre_census_argument(self.config.value["backup_root"], backup_root) != backup_root):
                raise ExecutiveSchemaUpgradeError("pre-census qualified config preimage differs")
            self.database_fd = os.open(database, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0))
            self.stack.callback(os.close, self.database_fd)
            self.database_identity = _pre_census_database_origin(database, self.database_fd, self.uid, self.gid)
            if self.database_identity != self.payload["database"]:
                raise ExecutiveSchemaUpgradeError("pre-census current database origin differs")
            self.backup_inventory = _pre_census_backup_inventory(backup_root)
            from ops.executive_os.acceptance_maintenance import digest
            if digest(self.backup_inventory) != self.payload["backup_inventory_sha256"]:
                raise ExecutiveSchemaUpgradeError("pre-census backup namespace differs from qualification")
            self.names = set(os.listdir(database.parent))
            self.check()
        except BaseException:
            self.stack.close()
            raise

    def check(self) -> None:
        if _pre_census_alias_identity() != self.alias_identity:
            raise ExecutiveSchemaUpgradeError("pre-census fixed system alias changed")
        if _marker_exists(self.marker):
            raise ExecutiveSchemaUpgradeError("pre-census service marker is present")
        _held_service_lock_identity(self.lock, self.lock_fd, self.lock_identity)
        if self.phase == "COMPLETE":
            self._check_removed_barrier()
        else:
            self.barrier.check()
        self.qualification.check()
        self.config.check()
        if self.intent is not None:
            self.intent.check()
        current_names = set(os.listdir(self.database.parent))
        journal_names = self._transaction_sidecars()
        if current_names != self.names | journal_names:
            raise ExecutiveSchemaUpgradeError("pre-census state namespace changed unexpectedly")
        if _pre_census_backup_inventory(self.backup_root) != self.backup_inventory:
            raise ExecutiveSchemaUpgradeError("pre-census backup namespace changed unexpectedly")
        info = _pre_census_database_metadata(self.database, self.database_fd, self.uid, self.gid)
        if (info.st_dev, info.st_ino) != (self.database_identity["device"], self.database_identity["inode"]):
            raise ExecutiveSchemaUpgradeError("pre-census authoritative database was replaced")
        if self.phase in {"SOURCE", "RESERVED"}:
            for name in (_UPGRADE_V5_TO_V6_PREFLIGHT_NAME, _UPGRADE_V5_TO_V6_COMPLETION_NAME,
                         _UPGRADE_V6_TO_V7_PREFLIGHT_NAME, _UPGRADE_V6_TO_V7_COMPLETION_NAME):
                if os.path.lexists(self.database.parent / name) and name not in self.normal_artifacts:
                    raise ExecutiveSchemaUpgradeError("pre-census normal receipt already exists")
            if any(os.path.lexists(_sidecar(self.database, suffix)) for suffix in _SIDECAR_SUFFIXES):
                raise ExecutiveSchemaUpgradeError("pre-census source database has a sidecar")
            if _pre_census_database_origin(self.database, self.database_fd, self.uid, self.gid) != self.payload["database"]:
                raise ExecutiveSchemaUpgradeError("pre-census current source database changed")
            before = _upgrade_v5_retained_state(self.database, version=5)
            for name in ("normalized_schema_digest", "full_v5_content_digest", "migration_vector"):
                if before[name] != self.payload[name]:
                    raise ExecutiveSchemaUpgradeError("pre-census exact-v5 source differs from qualification")
        _pre_census_prove_original_tool(self.payload["original_tool"])
        if _pre_census_release_record(_prove_upgrade_release(self.release_sha)) != self.payload["recovery_tool"]:
            raise ExecutiveSchemaUpgradeError("pre-census executor seal changed")

    def attach_transaction(self, connection: sqlite3.Connection) -> None:
        if self.phase != "DDL" or self.connection is not None or not isinstance(connection, sqlite3.Connection) or not connection.in_transaction:
            raise ExecutiveSchemaUpgradeError("pre-census sidecar scope requires the actual exclusive transaction")
        rows = [tuple(row) for row in connection.execute("PRAGMA database_list")]
        if rows != [(0, "main", str(self.database))]:
            raise ExecutiveSchemaUpgradeError("pre-census SQLite transaction targets another database")
        mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        if mode not in {"delete", "wal"}:
            raise ExecutiveSchemaUpgradeError("pre-census SQLite journal mode is unsupported")
        self.connection = connection
        self.journal_names = ({self.database.name + "-journal"} if mode == "delete" else
                              {self.database.name + "-wal", self.database.name + "-shm"})
        self.check()

    def _transaction_sidecars(self) -> set[str]:
        present = {self.database.name + suffix for suffix in _SIDECAR_SUFFIXES
                   if os.path.lexists(_sidecar(self.database, suffix))}
        if set(self.sidecar_fds) - present:
            raise ExecutiveSchemaUpgradeError("pre-census active transaction sidecar lost its name")
        if not present:
            return set()
        if (self.phase != "DDL" or self.connection is None
                or not self.connection.in_transaction or not present <= self.journal_names):
            raise ExecutiveSchemaUpgradeError("pre-census sidecar is not owned by the active transaction")
        from control_plane.fs_security import has_macos_acl
        for name in present:
            path = self.database.parent / name
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0))
            try:
                info, named = os.fstat(fd), os.lstat(path)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != self.uid or info.st_gid != self.gid
                        or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600
                        or _pre_census_stat(info) != _pre_census_stat(named)
                        or has_macos_acl(path, descriptor=fd, expected_identity=info)):
                    raise ExecutiveSchemaUpgradeError("pre-census transaction sidecar custody differs")
                pinned = self.sidecar_fds.get(name)
                if pinned is not None and (info.st_dev, info.st_ino) != pinned[1:]:
                    raise ExecutiveSchemaUpgradeError("pre-census transaction sidecar was replaced")
                if pinned is None:
                    self.sidecar_fds[name] = (fd, info.st_dev, info.st_ino)
                    fd = -1
            finally:
                if fd >= 0:
                    os.close(fd)
        return present

    def _close_transaction_sidecars(self) -> None:
        for fd, _device, _inode in self.sidecar_fds.values():
            os.close(fd)
        self.sidecar_fds.clear()

    def detach_transaction(self, connection: sqlite3.Connection) -> None:
        if self.connection is not connection:
            raise ExecutiveSchemaUpgradeError("pre-census transaction owner changed")
        try:
            connection.in_transaction
        except sqlite3.ProgrammingError:
            pass
        else:
            raise ExecutiveSchemaUpgradeError("pre-census transaction is still open")
        self.connection = None
        self.journal_names = set()
        self._close_transaction_sidecars()
        if any(os.path.lexists(_sidecar(self.database, suffix)) for suffix in _SIDECAR_SUFFIXES):
            raise ExecutiveSchemaUpgradeError("pre-census transaction left a sidecar after close")

    def census_rows(self) -> list[dict[str, Any]]:
        if self.intent is None or self.phase not in {"RESERVED", "DDL"}:
            raise RestoreSafetyError("recovered census requires its consumed typed operation")
        self.check()
        for path, fd in ((self.barrier.path, self.barrier.fd), (self.database, self.database_fd)):
            if fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY:
                raise RestoreSafetyError("recovered census retained artifact FD is not read-only")
            info, named = os.fstat(fd), os.lstat(path)
            if ((info.st_dev, info.st_ino) != (named.st_dev, named.st_ino)
                    or info.st_uid != self.uid or info.st_gid != self.gid
                    or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
                raise RestoreSafetyError("recovered census retained artifact FD custody changed")
        rows = [{"pid": os.getpid(), "uid": self.uid, "fd": str(fd), "path": str(path)}
                for path, fd in ((self.lock, self.lock_fd), (self.barrier.path, self.barrier.fd),
                                 (self.database, self.database_fd))]
        if len({row["fd"] for row in rows}) != 3:
            raise RestoreSafetyError("recovered census descriptor identity is ambiguous")
        return sorted(rows, key=lambda row: int(row["fd"]))

    def reserve(self) -> None:
        if self.intent is not None or self.phase != "SOURCE":
            raise ExecutiveSchemaUpgradeError("pre-census intent cannot be reserved twice")
        self.check()
        value = {"schema_version": PRE_CENSUS_CONTINUATION_SCHEMA,
                 "operation_id": self.barrier.payload["operation_id"],
                 "original_barrier_identity": self.barrier.identity,
                 "qualification_identity": self.qualification.identity,
                 "recovery_tool": self.payload["recovery_tool"], "created_at": _upgrade_now()}
        _write_private_json(self.intent_path, value)
        if set(os.listdir(self.database.parent)) != self.names | {PRE_CENSUS_CONTINUATION_NAME}:
            raise ExecutiveSchemaUpgradeError("pre-census intent namespace transition differs")
        self.names.add(PRE_CENSUS_CONTINUATION_NAME)
        self.intent = _PreCensusReceiptObservation(self.intent_path, uid=self.uid, gid=self.gid, mode=0o600)
        self.stack.callback(self.intent.close)
        if self.intent.payload != value:
            raise ExecutiveSchemaUpgradeError("pre-census consumed intent differs")
        self.phase = "RESERVED"
        self.check()

    def accept_state_artifact(self, path: Path) -> None:
        if path.parent != self.database.parent or path.name not in {_UPGRADE_V5_TO_V6_PREFLIGHT_NAME, _UPGRADE_V5_TO_V6_COMPLETION_NAME}:
            raise ExecutiveSchemaUpgradeError("pre-census unexpected state artifact")
        if set(os.listdir(path.parent)) != self.names | {path.name}:
            raise ExecutiveSchemaUpgradeError("pre-census state publication changed another name")
        self.names.add(path.name)
        self.normal_artifacts.add(path.name)

    def accept_backup(self, receipt: Any) -> None:
        current = _pre_census_backup_inventory(self.backup_root)
        paths = {receipt.database_path, receipt.manifest_path}
        if set(current) != set(self.backup_inventory) | paths:
            raise ExecutiveSchemaUpgradeError("pre-census backup publication changed another name")
        if any(current[path] != value for path, value in self.backup_inventory.items()):
            raise ExecutiveSchemaUpgradeError("pre-census retained backup changed")
        for path, sha in ((receipt.database_path, receipt.database_sha256), (receipt.manifest_path, receipt.manifest_sha256)):
            row = current[path]
            if row != {"uid": self.uid, "gid": self.gid, "mode": 0o600, "nlink": 1, "sha256": sha}:
                raise ExecutiveSchemaUpgradeError("pre-census produced backup custody differs")
        self.backup_inventory = current

    def begin_ddl(self) -> None:
        if self.phase != "RESERVED" or self.intent is None:
            raise ExecutiveSchemaUpgradeError("pre-census DDL requires the consumed intent")
        # P56 was just written by this owner, so its expected name is retained;
        # all immutable source proof was checked before that publication.
        self.check()
        self.phase = "DDL"

    def _check_removed_barrier(self) -> None:
        held = os.fstat(self.barrier.fd)
        if (held.st_dev, held.st_ino) != (self.barrier.identity["device"], self.barrier.identity["inode"]) or held.st_nlink != 0 or os.path.lexists(self.barrier.path):
            raise ExecutiveSchemaUpgradeError("pre-census final removal did not remove original held barrier")

    def mark_barrier_removed(self) -> None:
        self._check_removed_barrier()
        self.names.remove(self.barrier.path.name)
        self.phase = "COMPLETE"
        self.check()

    def close(self) -> None:
        self.stack.close()


def _pre_census_upgrade_census(recovery: _PreCensusContinuation) -> dict[str, Any]:
    if not isinstance(recovery, _PreCensusContinuation):
        raise RestoreSafetyError("recovered census requires the internally qualified owner")
    recovery.census_rows()
    raw = _default_upgrade_census_with_context(recovery.database, recovery.lock,
            recovery.barrier.path, recovery.lock_fd, recovery)
    material = _validate_upgrade_census(raw, recovery.database, recovery.lock,
                                      recovery.barrier.path, recovery.lock_fd, recovery)
    recovery.census_rows()
    return material


def resume_v5_to_v6_pre_census(database_path: str | Path, backup_directory: str | Path, *,
                              release_sha: str, expected_operation_id: str,
                              expected_barrier_sha256: str) -> SchemaUpgradeV5ToV6Receipt:
    """Consume one Root qualification for the SAME original fixed operation."""
    _pre_census_hash(expected_operation_id, length=32)
    _pre_census_hash(expected_barrier_sha256)
    uid, gid = _pre_census_control_identity()
    if os.geteuid() != uid or os.getegid() != gid:
        raise ExecutiveSchemaUpgradeError("pre-census continuation requires fixed Control caller")
    database = _pre_census_argument(database_path, _PRE_CENSUS_DATABASE)
    backup_root = _pre_census_argument(backup_directory, database.parents[3] / "backups")
    if os.path.lexists(database.parent / PRE_CENSUS_CONTINUATION_NAME):
        raise ExecutiveSchemaUpgradeError("pre-census intent already exists; same-operation execution is not replayable")
    lock, marker = database.parent / DEFAULT_SERVICE_LOCK_NAME, database.parent / DEFAULT_SERVICE_MARKER_NAME
    with _offline_restore_lock(lock, marker, require_existing=True) as lock_fd:
        continuation = _PreCensusContinuation(database, backup_root, release_sha,
                                              expected_operation_id, expected_barrier_sha256, lock_fd)
        try:
            continuation.reserve()
            return _upgrade_v5_to_v6_impl(database, backup_root, release_sha=release_sha, _recovery=continuation)
        finally:
            continuation.close()


def upgrade_v5_to_v6(
    database_path: str | Path, backup_directory: str | Path, *, release_sha: str,
) -> SchemaUpgradeV5ToV6Receipt:
    """Ordinary new-operation transition; existing barrier/receipt always refuses."""
    return _upgrade_v5_to_v6_impl(database_path, backup_directory, release_sha=release_sha)


def _upgrade_v5_to_v6_impl(
    database_path: str | Path,
    backup_directory: str | Path,
    *,
    release_sha: str,
    _recovery: _PreCensusContinuation | None = None,
) -> SchemaUpgradeV5ToV6Receipt:
    """Upgrade one exact offline v5 store to v6 using the retained custody chain.

    Installed release, canonical service lock, writer census, source and target
    backups with restore drills, exclusive DDL, and quarantine rules match the
    v4-to-v5 transition. Only migration 6 is executed; no caller-supplied SQL or
    arbitrary source/target version is accepted. All eight retained tables and
    original migration receipts 1-5 must remain byte-for-byte logically equal.
    """

    release = _prove_upgrade_release(release_sha)
    candidate = Path(database_path).expanduser()
    _assert_private_regular_file(candidate, label="Executive exact-v5 database")
    database = candidate.resolve(strict=True)
    state_directory = database.parent
    marker = state_directory / DEFAULT_SERVICE_MARKER_NAME
    lock = state_directory / DEFAULT_SERVICE_LOCK_NAME
    barrier = state_directory / _UPGRADE_BARRIER_NAME
    preflight_path = state_directory / _UPGRADE_V5_TO_V6_PREFLIGHT_NAME
    completion_path = state_directory / _UPGRADE_V5_TO_V6_COMPLETION_NAME
    if _recovery is None and any(os.path.lexists(state_directory / name) for name in
                                  (PRE_CENSUS_QUALIFICATION_NAME, PRE_CENSUS_CONTINUATION_NAME)):
        raise ExecutiveSchemaUpgradeError("pre-census recovery residue forbids a new v5-to-v6 operation")
    if _recovery is None and any(os.path.lexists(path) for path in (barrier, preflight_path, completion_path)):
        raise ExecutiveSchemaUpgradeError(
            "v5-to-v6 upgrade barrier/receipt already exists; explicit operator "
            "reconciliation required before another attempt"
        )
    operation_id = uuid4().hex if _recovery is None else _recovery.barrier.payload["operation_id"]
    created_at = _upgrade_now() if _recovery is None else _recovery.barrier.payload["created_at"]
    barrier_payload = {
        "schema_version": UPGRADE_BARRIER_SCHEMA,
        "operation_id": operation_id,
        "database_path": str(database),
        "tool_release_root": release["release_root"],
        "tool_release_tree_sha": release["release_tree_sha"],
        "tool_release_manifest_sha256": release["release_manifest_sha256"],
        "release_sha": release["release_sha"],
        "control_uid": os.geteuid(),
        "created_at": created_at,
    }
    if _recovery is not None:
        barrier_payload = dict(_recovery.barrier.payload)
    before: dict[str, Any] | None = None
    preflight: dict[str, Any] | None = None
    barrier_identity: dict[str, Any] | None = None
    preflight_identity: dict[str, Any] | None = None
    census: dict[str, Any] | None = None
    committed_v6 = False
    recovered_completion_identity = None
    with (_offline_restore_lock(lock, marker, require_existing=True) if _recovery is None else nullcontext(_recovery.lock_fd)) as lock_fd:
        lock_identity = _held_service_lock_identity(lock, lock_fd)
        def current_census() -> dict[str, Any]:
            return (_upgrade_census(database, lock, barrier, lock_fd) if _recovery is None
                    else _pre_census_upgrade_census(_recovery))
        if _recovery is None:
            _write_private_json(barrier, barrier_payload)
        else:
            _recovery.check()
        barrier_identity = _artifact_identity(
            barrier, expected_payload=barrier_payload
        )
        try:
            _upgrade_hook("barrier_persisted")
            _artifact_identity(
                barrier,
                expected_payload=barrier_payload,
                expected=barrier_identity,
            )
            if _marker_exists(marker):
                raise RestoreSafetyError("Executive service marker appeared before census")
            census = current_census()
            _checkpoint_quiesced_wal(database)
            if current_census() != census:
                raise RestoreSafetyError("writer census changed across WAL checkpoint")
            before = _upgrade_v5_retained_state(database, version=5)
            v5_backup = create_offline_backup(
                database, backup_directory, expected_schema_version=5
            )
            v5_drill = verify_restore_drill(
                v5_backup.database_path,
                v5_backup.manifest_path,
                expected_schema_version=5,
            )
            with _readonly_database(Path(v5_backup.database_path)) as connection:
                backup_full_v4 = full_v4_content_digest(connection)
                backup_m5 = _v5_migration_receipt_digest(connection)
            if (
                v5_backup.legacy_content_digest != before["legacy_content_digest"]
                or v5_drill.legacy_content_digest != before["legacy_content_digest"]
                or v5_backup.normalized_schema_digest
                != before["normalized_schema_digest"]
                or v5_drill.normalized_schema_digest
                != before["normalized_schema_digest"]
                or backup_full_v4 != before["full_v4_content_digest"]
                or backup_m5 != before["v5_migration_receipt_digest"]
            ):
                raise ExecutiveSchemaUpgradeError("v5 source/backup/drill proof differs")
            preflight = {
                "schema_version": UPGRADE_PREFLIGHT_SCHEMA,
                "operation_id": operation_id,
                "source_schema_version": 5,
                "target_schema_version": 6,
                "database": before["database"],
                "migration_vector": before["migration_vector"],
                "normalized_schema_digest": before["normalized_schema_digest"],
                "full_v4_content_digest": before["full_v4_content_digest"],
                "v5_migration_receipt_digest": before["v5_migration_receipt_digest"],
                "barrier_identity": barrier_identity,
                "v5_backup": {
                    "database_path": v5_backup.database_path,
                    "database_sha256": v5_backup.database_sha256,
                    "manifest_path": v5_backup.manifest_path,
                    "manifest_sha256": v5_backup.manifest_sha256,
                    "restore_drill_receipt": v5_drill.to_dict(),
                    "restore_drill_digest": _upgrade_digest(v5_drill.to_dict()),
                    "full_v4_content_digest": backup_full_v4,
                },
                "quiesce_writer_census": census,
                "quiesce_writer_census_digest": _upgrade_digest(census),
                "tool_release_root": release["release_root"],
                "tool_release_tree_sha": release["release_tree_sha"],
                "tool_release_manifest_sha256": release[
                    "release_manifest_sha256"
                ],
                "release_sha": release["release_sha"],
                "created_at": created_at,
            }
            if _recovery is not None:
                _recovery.accept_backup(v5_backup)
                _recovery.check()
                preflight["schema_version"] = PRE_CENSUS_PREFLIGHT_SCHEMA
                preflight["pre_census_reconciliation"] = {
                    "qualification_identity": dict(_recovery.qualification.identity),
                    "continuation_identity": dict(_recovery.intent.identity),
                }
            _write_private_json(preflight_path, preflight)
            if _recovery is not None:
                _recovery.accept_state_artifact(preflight_path)
            preflight_identity = _artifact_identity(
                preflight_path, expected_payload=preflight
            )
            preflight_digest = _upgrade_digest(preflight)
            if _recovery is not None:
                _recovery.begin_ddl()
            _upgrade_hook("preflight_persisted")

            def revalidate_control_artifacts() -> None:
                if _recovery is not None:
                    _recovery.check()
                if _marker_exists(marker):
                    raise RestoreSafetyError(
                        "Executive service marker appeared during schema upgrade"
                    )
                _held_service_lock_identity(lock, lock_fd, lock_identity)
                _artifact_identity(
                    barrier,
                    expected_payload=barrier_payload,
                    expected=barrier_identity,
                )
                _artifact_identity(
                    preflight_path,
                    expected_payload=preflight,
                    expected=preflight_identity,
                )
                if _prove_upgrade_release(release_sha) != release:
                    raise ExecutiveSchemaUpgradeError("tool release identity changed")
                _assert_upgrade_database_inode(database, before)

            def revalidate_v5_backup_proof() -> None:
                checked = verify_backup(
                    v5_backup.database_path,
                    v5_backup.manifest_path,
                    expected_schema_version=5,
                )
                checked_drill = verify_restore_drill(
                    v5_backup.database_path,
                    v5_backup.manifest_path,
                    expected_schema_version=5,
                )
                with _readonly_database(Path(v5_backup.database_path)) as connection:
                    checked_full_v4 = full_v4_content_digest(connection)
                    checked_m5 = _v5_migration_receipt_digest(connection)
                if (
                    checked.database_sha256 != v5_backup.database_sha256
                    or checked.manifest_sha256 != v5_backup.manifest_sha256
                    or checked.normalized_schema_digest
                    != v5_backup.normalized_schema_digest
                    or checked.legacy_content_digest
                    != v5_backup.legacy_content_digest
                    or checked_full_v4 != backup_full_v4
                    or checked_m5 != backup_m5
                    or checked_drill.to_dict() != v5_drill.to_dict()
                    or _upgrade_digest(checked_drill.to_dict())
                    != preflight["v5_backup"]["restore_drill_digest"]
                ):
                    raise ExecutiveSchemaUpgradeError(
                        "v5 backup or restore-drill proof changed after preflight"
                    )

            revalidate_control_artifacts()
            revalidate_v5_backup_proof()
            if _upgrade_v5_retained_state(database, version=5) != before:
                raise ExecutiveSchemaUpgradeError("v5 source changed after preflight")
            if current_census() != census:
                raise RestoreSafetyError("writer census changed before migration")

            connection = sqlite3.connect(database, isolation_level=None, timeout=5.0)
            connection.row_factory = sqlite3.Row
            try:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("BEGIN EXCLUSIVE")
                if _recovery is not None:
                    _recovery.attach_transaction(connection)
                revalidate_control_artifacts()
                _verify_connection(connection, expected_schema_version=5)
                if (full_v4_content_digest(connection) != before["full_v4_content_digest"]
                        or _v5_migration_receipt_digest(connection)
                        != before["v5_migration_receipt_digest"]):
                    raise ExecutiveSchemaUpgradeError("in-transaction v5 content changed")
                _upgrade_hook("exclusive_v5_verified")
                revalidate_control_artifacts()
                version, name, statements = _MIGRATIONS[5]
                if version != 6:
                    raise ExecutiveSchemaUpgradeError("reviewed migration 6 is unavailable")
                for ordinal, statement in enumerate(statements, 1):
                    connection.execute(statement)
                    if _recovery is not None:
                        _recovery._transaction_sidecars()
                    _upgrade_hook(f"after_m6_statement:{ordinal:02d}")
                    revalidate_control_artifacts()
                connection.execute(
                    """
                    INSERT INTO schema_migrations(version,name,checksum,applied_at_ms)
                    VALUES(?,?,?,?)
                    """,
                    (
                        version,
                        name,
                        _migration_checksum(statements),
                        int(datetime.now(UTC).timestamp() * 1000),
                    ),
                )
                _upgrade_hook("after_m6_receipt")
                revalidate_control_artifacts()
                _verify_connection(connection, expected_schema_version=6)
                if (full_v4_content_digest(connection) != before["full_v4_content_digest"]
                        or _v5_migration_receipt_digest(connection)
                        != before["v5_migration_receipt_digest"]):
                    raise ExecutiveSchemaUpgradeError("migration changed full v4 content")
                _upgrade_hook("before_v6_commit")
                revalidate_control_artifacts()
                _verify_connection(connection, expected_schema_version=6)
                if (full_v4_content_digest(connection) != before["full_v4_content_digest"]
                        or _v5_migration_receipt_digest(connection)
                        != before["v5_migration_receipt_digest"]):
                    raise ExecutiveSchemaUpgradeError("precommit full v4 content drifted")
                connection.commit()
                committed_v6 = True
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()
                if _recovery is not None and _recovery.connection is connection:
                    _recovery.detach_transaction(connection)

            _upgrade_hook("after_v6_commit_before_checkpoint")
            revalidate_control_artifacts()
            _checkpoint_quiesced_wal(database)
            _upgrade_hook("after_v6_checkpoint")
            revalidate_control_artifacts()
            verified_v6 = _upgrade_v5_retained_state(database, version=6)
            if verified_v6["legacy_content_digest"] != before["legacy_content_digest"]:
                raise ExecutiveSchemaUpgradeError("committed v6 legacy content differs")
            with _readonly_database(database) as connection:
                committed_full_v4 = full_v4_content_digest(connection)
            if (committed_full_v4 != before["full_v4_content_digest"]
                    or verified_v6["v5_migration_receipt_digest"]
                    != before["v5_migration_receipt_digest"]):
                raise ExecutiveSchemaUpgradeError("committed v6 full v4 content differs")
            v6_backup = create_offline_backup(
                database, backup_directory, expected_schema_version=6
            )
            v6_drill = verify_restore_drill(
                v6_backup.database_path,
                v6_backup.manifest_path,
                expected_schema_version=6,
            )
            with _readonly_database(Path(v6_backup.database_path)) as connection:
                v6_backup_full_v4 = full_v4_content_digest(connection)
                v6_backup_m5 = _v5_migration_receipt_digest(connection)
            if (
                v6_backup.legacy_content_digest != before["legacy_content_digest"]
                or v6_drill.legacy_content_digest != before["legacy_content_digest"]
                or v6_backup.normalized_schema_digest
                != verified_v6["normalized_schema_digest"]
                or v6_drill.normalized_schema_digest
                != verified_v6["normalized_schema_digest"]
                or v6_backup_full_v4 != before["full_v4_content_digest"]
                or v6_backup_m5 != before["v5_migration_receipt_digest"]
            ):
                raise ExecutiveSchemaUpgradeError("v6 source/backup/drill proof differs")
            if _recovery is not None:
                _recovery.accept_backup(v6_backup)
            if current_census() != census:
                raise RestoreSafetyError("writer census changed before completion")
            revalidate_control_artifacts()
            completed_at = _upgrade_now()
            completion = {
                "schema_version": UPGRADE_COMPLETION_SCHEMA,
                "operation_id": operation_id,
                "source_schema_version": 5,
                "target_schema_version": 6,
                "preflight_receipt_digest": preflight_digest,
                "authoritative_v6_database": verified_v6["database"],
                "authoritative_v6_schema_digest": verified_v6[
                    "normalized_schema_digest"
                ],
                "migration_vector": verified_v6["migration_vector"],
                "pre_full_v4_content_digest": before["full_v4_content_digest"],
                "post_full_v4_content_digest": committed_full_v4,
                "pre_v5_migration_receipt_digest": before["v5_migration_receipt_digest"],
                "post_v5_migration_receipt_digest": verified_v6["v5_migration_receipt_digest"],
                "full_v4_content_equal": True,
                "pre_v4_legacy_content_digest": before["legacy_content_digest"],
                "post_v4_legacy_content_digest": verified_v6[
                    "legacy_content_digest"
                ],
                "legacy_content_equal": True,
                "v6_backup": {
                    "database_path": v6_backup.database_path,
                    "database_sha256": v6_backup.database_sha256,
                    "manifest_path": v6_backup.manifest_path,
                    "manifest_sha256": v6_backup.manifest_sha256,
                    "restore_drill_receipt": v6_drill.to_dict(),
                    "restore_drill_digest": _upgrade_digest(v6_drill.to_dict()),
                    "full_v4_content_digest": v6_backup_full_v4,
                },
                "quiesce_writer_census_digest": _upgrade_digest(census),
                "tool_release_root": release["release_root"],
                "tool_release_tree_sha": release["release_tree_sha"],
                "tool_release_manifest_sha256": release[
                    "release_manifest_sha256"
                ],
                "release_sha": release["release_sha"],
                "completed_at": completed_at,
            }
            if _recovery is None:
                _write_private_json(completion_path, completion)
                completion_identity = _artifact_identity(
                    completion_path, expected_payload=completion
                )
                _upgrade_hook("completion_persisted")
            else:
                # A recovered C56 is a durable completion fact only AFTER
                # final proof and exact removal of the held original barrier.
                _recovery.check()
            # The final adversarial seam is deliberately placed before the
            # complete authoritative/backup/drill/census proof.  Nothing after
            # this hook may escape revalidation before the barrier is removed.
            _upgrade_hook("before_barrier_unlink")
            revalidate_control_artifacts()
            if _recovery is None:
                _artifact_identity(
                    completion_path,
                    expected_payload=completion,
                    expected=completion_identity,
                )
            final_v6 = _upgrade_v5_retained_state(database, version=6)
            final_v6_backup = verify_backup(
                v6_backup.database_path,
                v6_backup.manifest_path,
                expected_schema_version=6,
            )
            final_v6_drill = verify_restore_drill(
                v6_backup.database_path,
                v6_backup.manifest_path,
                expected_schema_version=6,
            )
            with _readonly_database(database) as connection:
                final_full_v4 = full_v4_content_digest(connection)
            if (
                final_v6 != verified_v6
                or final_full_v4 != before["full_v4_content_digest"]
                or final_v6_backup.database_sha256 != v6_backup.database_sha256
                or final_v6_backup.manifest_sha256 != v6_backup.manifest_sha256
                or final_v6_backup.normalized_schema_digest
                != v6_backup.normalized_schema_digest
                or final_v6_backup.legacy_content_digest
                != v6_backup.legacy_content_digest
                or final_v6_drill.to_dict() != v6_drill.to_dict()
                or _upgrade_digest(final_v6_drill.to_dict())
                != completion["v6_backup"]["restore_drill_digest"]
            ):
                raise ExecutiveSchemaUpgradeError(
                    "completion v6 source/backup/drill proof changed"
                )
            # The retained source backup stays in custody after the commit, so
            # it is revalidated beside the final v6 proof before release.
            revalidate_v5_backup_proof()
            if current_census() != census:
                raise RestoreSafetyError("writer census changed before barrier release")
            revalidate_control_artifacts()
            if _recovery is None:
                _artifact_identity(
                    completion_path,
                    expected_payload=completion,
                    expected=completion_identity,
                )
            _unlink_exact_upgrade_artifact(
                barrier,
                expected_payload=barrier_payload,
                expected=barrier_identity,
            )
            if _recovery is not None:
                _recovery.mark_barrier_removed()
                _upgrade_hook("recovered_barrier_removed_before_completion")
                _recovery.check()
                final_origin = _pre_census_database_origin(database, _recovery.database_fd,
                    _recovery.uid, _recovery.gid)
                if {key: final_origin[key] for key in ("path", "device", "inode", "size", "sha256")} != verified_v6["database"]:
                    raise ExecutiveSchemaUpgradeError("recovered final database changed before completion")
                _write_private_json(completion_path, completion)
                _recovery.accept_state_artifact(completion_path)
                recovered_completion_identity = _artifact_identity(completion_path, expected_payload=completion)
                _recovery.check()
                _upgrade_hook("completion_persisted")
            return SchemaUpgradeV5ToV6Receipt(
                schema_version=UPGRADE_COMPLETION_SCHEMA,
                database_path=str(database),
                database_identity=dict(verified_v6["database"]),
                release_sha=release["release_sha"],
                preflight_receipt_path=str(preflight_path),
                preflight_receipt_digest=preflight_digest,
                completion_receipt_path=str(completion_path),
                completion_receipt_digest=_upgrade_digest(completion),
                source_schema_version=5,
                target_schema_version=6,
                pre_full_v4_content_digest=before["full_v4_content_digest"],
                post_full_v4_content_digest=committed_full_v4,
                pre_v5_migration_receipt_digest=before["v5_migration_receipt_digest"],
                post_v5_migration_receipt_digest=verified_v6["v5_migration_receipt_digest"],
                full_v4_content_equal=True,
                v5_backup_path=v5_backup.database_path,
                v5_backup_manifest_path=v5_backup.manifest_path,
                v6_backup_path=v6_backup.database_path,
                v6_backup_manifest_path=v6_backup.manifest_path,
                completed_at=completed_at,
            )
        except Exception as exc:
            if _recovery is not None:
                if recovered_completion_identity is not None:
                    raise ExecutiveSchemaUpgradeError(
                        "recovered v6 completion is durable; same-operation result inspection only"
                    ) from exc
                # The consumed one-use intent is the quarantine even if an
                # external actor removed the original barrier. Never recreate,
                # rewrite or unlink it and never enter ordinary rollback cleanup.
                raise ExecutiveSchemaUpgradeError(
                    "pre-census continuation failed; intent retained, same-operation inspection only"
                ) from exc
            if committed_v6:
                _ensure_upgrade_quarantine_barrier(barrier, barrier_payload)
                raise ExecutiveSchemaUpgradeError(
                    "v6 committed but completion failed; barrier remains for forward fix"
                ) from exc
            if before is None or barrier_identity is None or census is None:
                _ensure_upgrade_quarantine_barrier(barrier, barrier_payload)
                raise ExecutiveSchemaUpgradeError(
                    "precommit upgrade failed before exact rollback proof; barrier remains"
                ) from exc
            try:
                _upgrade_hook("after_precommit_rollback_before_guard")
                current = _upgrade_v5_retained_state(database, version=5)
                if (not _rollback_reproduces_preflight(current, before)
                        or current["v5_migration_receipt_digest"]
                        != before["v5_migration_receipt_digest"]):
                    raise ExecutiveSchemaUpgradeError(
                        "rolled-back v5 state differs from frozen preflight"
                    )
                if _prove_upgrade_release(release_sha) != release:
                    raise ExecutiveSchemaUpgradeError(
                        "tool release identity changed before rollback cleanup"
                    )
                if current_census() != census:
                    raise RestoreSafetyError(
                        "writer census changed before rollback barrier release"
                    )
                if _marker_exists(marker):
                    raise RestoreSafetyError(
                        "Executive service marker appeared before rollback cleanup"
                    )
                _held_service_lock_identity(lock, lock_fd, lock_identity)
                _artifact_identity(
                    barrier,
                    expected_payload=barrier_payload,
                    expected=barrier_identity,
                )
                if preflight is not None and preflight_identity is not None:
                    _artifact_identity(
                        preflight_path,
                        expected_payload=preflight,
                        expected=preflight_identity,
                    )
                    _unlink_exact_upgrade_artifact(
                        preflight_path,
                        expected_payload=preflight,
                        expected=preflight_identity,
                    )
                _unlink_exact_upgrade_artifact(
                    barrier,
                    expected_payload=barrier_payload,
                    expected=barrier_identity,
                )
            except Exception as guard_exc:
                _ensure_upgrade_quarantine_barrier(barrier, barrier_payload)
                raise ExecutiveSchemaUpgradeError(
                    "v5 rollback did not reproduce preflight; barrier remains"
                ) from guard_exc
            raise ExecutiveSchemaUpgradeError(
                f"v5 migration rolled back without v6 commit: {type(exc).__name__}: {exc}"
            ) from exc


@contextmanager
def _completed_pre_census_recovery(database: Path, backup_root: Path, release: Mapping[str, str]) -> Iterator[Any]:
    """Allow normal 6→7 only after the one-use recovered 5→6 actually completed.

    This Control-owned finite gate does not import the Root four-receipt helper.
    All immutable origins stay held while the normal next owner executes.
    """
    names = (PRE_CENSUS_QUALIFICATION_NAME, PRE_CENSUS_CONTINUATION_NAME)
    if not any(os.path.lexists(database.parent / name) for name in names):
        yield None
        return
    uid, gid = _pre_census_control_identity()
    if (os.geteuid(), os.getegid()) != (uid, gid) or database != _PRE_CENSUS_DATABASE:
        raise ExecutiveSchemaUpgradeError("recovered completion requires the fixed Control owner/database")
    if backup_root != database.parents[3] / "backups":
        raise ExecutiveSchemaUpgradeError("recovered completion backup root differs")
    with ExitStack() as stack:
        held = []
        for name, owner, mode in ((names[0], 0, 0o440), (names[1], uid, 0o600),
                (_UPGRADE_V5_TO_V6_PREFLIGHT_NAME, uid, 0o600),
                (_UPGRADE_V5_TO_V6_COMPLETION_NAME, uid, 0o600)):
            try:
                obs = _PreCensusReceiptObservation(database.parent / name, uid=owner, gid=gid, mode=mode)
            except (OSError, BackupVerificationError) as exc:
                raise ExecutiveSchemaUpgradeError("recovered completion receipt is missing or unsafe") from exc
            stack.callback(obs.close); held.append(obs)
        qualification, intent, preflight, completion = held
        q = _validate_pre_census_qualification(qualification.payload)
        i, p, c = intent.payload, preflight.payload, completion.payload
        expected_i = {"schema_version": PRE_CENSUS_CONTINUATION_SCHEMA,
            "operation_id": q["operation_id"], "original_barrier_identity": q["original_barrier"]["identity"],
            "qualification_identity": qualification.identity, "recovery_tool": q["recovery_tool"],
            "created_at": i.get("created_at")}
        _pre_census_time(i.get("created_at"))
        refs = {"qualification_identity": qualification.identity, "continuation_identity": intent.identity}
        common = {"schema_version", "operation_id", "source_schema_version", "target_schema_version",
            "tool_release_root", "tool_release_tree_sha", "tool_release_manifest_sha256", "release_sha"}
        pk = common | {"database", "migration_vector", "normalized_schema_digest", "barrier_identity",
            "quiesce_writer_census", "quiesce_writer_census_digest", "created_at",
            "full_v4_content_digest", "v5_migration_receipt_digest", "v5_backup", "pre_census_reconciliation"}
        ck = common | {"preflight_receipt_digest", "migration_vector", "quiesce_writer_census_digest",
            "completed_at", "authoritative_v6_database", "authoritative_v6_schema_digest",
            "pre_full_v4_content_digest", "post_full_v4_content_digest", "pre_v5_migration_receipt_digest",
            "post_v5_migration_receipt_digest", "full_v4_content_equal", "pre_v4_legacy_content_digest",
            "post_v4_legacy_content_digest", "legacy_content_equal", "v6_backup"}
        if (set(p) != pk or set(c) != ck or i != expected_i
                or p["schema_version"] != PRE_CENSUS_PREFLIGHT_SCHEMA
                or c["schema_version"] != UPGRADE_COMPLETION_SCHEMA
                or p["pre_census_reconciliation"] != refs
                or p["barrier_identity"] != q["original_barrier"]["identity"]
                or p["created_at"] != q["original_barrier"]["payload"]["created_at"]
                or q["recovery_tool"] != _pre_census_release_record(release)
                or p["database"] != {key: q["database"][key] for key in ("path", "device", "inode", "size", "sha256")}
                or p["migration_vector"] != q["migration_vector"]
                or p["normalized_schema_digest"] != q["normalized_schema_digest"]
                or c["preflight_receipt_digest"] != _upgrade_digest(p)):
            raise ExecutiveSchemaUpgradeError("recovered 5-to-6 completion wire differs")
        for receipt in (p, c):
            if (receipt["operation_id"] != q["operation_id"]
                    or receipt["source_schema_version"] != 5 or receipt["target_schema_version"] != 6
                    or _pre_census_release_record({"release_root": receipt["tool_release_root"],
                        "release_sha": receipt["release_sha"], "release_tree_sha": receipt["tool_release_tree_sha"],
                        "release_manifest_sha256": receipt["tool_release_manifest_sha256"]}) != q["recovery_tool"]):
                raise ExecutiveSchemaUpgradeError("recovered completion operation/tool differs")
        census = p["quiesce_writer_census"]
        census_keys = {"schema_version", "control_uids", "upgrader_pid", "inspected_paths",
            "process_sensor", "file_sensor", "processes", "open_files"}
        expected_paths = [str(database), *(str(_sidecar(database, x)) for x in _SIDECAR_SUFFIXES),
            str(database.parent / DEFAULT_SERVICE_LOCK_NAME), str(database.parent / _UPGRADE_BARRIER_NAME)]
        if (not isinstance(census, dict) or set(census) != census_keys
                or census["schema_version"] != PRE_CENSUS_CENSUS_SCHEMA
                or census["control_uids"] != [uid] or type(census["upgrader_pid"]) is not int
                or census["upgrader_pid"] <= 0 or census["processes"] != []
                or census["inspected_paths"] != expected_paths
                or census["process_sensor"] != {"binary": "/bin/ps", "upgrader_observed": True, "sensor_child_observed": True}
                or census["file_sensor"] != {"binary": "/usr/sbin/lsof", "held_lock_observed": True}):
            raise ExecutiveSchemaUpgradeError("recovered completion census differs")
        rows = census["open_files"]
        if (not isinstance(rows, list) or len(rows) != 3
                or any(not isinstance(row, dict) or set(row) != {"pid", "uid", "fd", "path"}
                    or row["pid"] != census["upgrader_pid"] or type(row["pid"]) is not int
                    or row["uid"] != uid or type(row["uid"]) is not int
                    or not isinstance(row["fd"], str) or re.fullmatch(r"[0-9]+", row["fd"]) is None for row in rows)
                or len({int(row["fd"]) for row in rows}) != 3
                or rows != sorted(rows, key=lambda row: int(row["fd"]))
                or {row["path"] for row in rows} != {str(database), expected_paths[-2], expected_paths[-1]}
                or p["quiesce_writer_census_digest"] != _upgrade_digest(census)
                or c["quiesce_writer_census_digest"] != _upgrade_digest(census)):
            raise ExecutiveSchemaUpgradeError("recovered completion held census differs")
        backups = []
        for version, receipt in ((5, p), (6, c)):
            pair = _pre_census_closed(receipt[f"v{version}_backup"], frozenset({"database_path", "database_sha256",
                "manifest_path", "manifest_sha256", "restore_drill_receipt", "restore_drill_digest", "full_v4_content_digest"}), "completion backup")
            for key, hashkey in (("database_path", "database_sha256"), ("manifest_path", "manifest_sha256")):
                path = Path(pair[key])
                if path.parent != backup_root or path.name in {"", ".", ".."}:
                    raise ExecutiveSchemaUpgradeError("recovered completion backup origin differs")
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0))
                stack.callback(os.close, fd)
                origin = _pre_census_database_origin(path, fd, uid, gid)
                if origin["sha256"] != pair[hashkey]:
                    raise ExecutiveSchemaUpgradeError("recovered completion backup hash differs")
                backups.append((path, fd, origin))
            verified = verify_backup(pair["database_path"], pair["manifest_path"], expected_schema_version=version)
            drill = verify_restore_drill(pair["database_path"], pair["manifest_path"], expected_schema_version=version)
            if (_upgrade_digest(drill.to_dict()) != pair["restore_drill_digest"]
                    or json.loads(json.dumps(drill.to_dict())) != pair["restore_drill_receipt"]
                    or verified.database_sha256 != pair["database_sha256"]
                    or verified.manifest_sha256 != pair["manifest_sha256"]):
                raise ExecutiveSchemaUpgradeError("recovered completion backup/drill differs")
            with _readonly_database(Path(pair["database_path"])) as connection:
                full4, m5 = full_v4_content_digest(connection), _v5_migration_receipt_digest(connection)
                if version == 5 and full_v5_content_digest(connection) != q["full_v5_content_digest"]:
                    raise ExecutiveSchemaUpgradeError("recovered completion original full-v5 differs")
            if (full4 != pair["full_v4_content_digest"] or full4 != p["full_v4_content_digest"]
                    or m5 != p["v5_migration_receipt_digest"]):
                raise ExecutiveSchemaUpgradeError("recovered completion retained content differs")
        current = _upgrade_v5_retained_state(database, version=6)
        if (current["database"] != c["authoritative_v6_database"]
                or current["normalized_schema_digest"] != c["authoritative_v6_schema_digest"]
                or current["migration_vector"] != c["migration_vector"]
                or c["full_v4_content_equal"] is not True or c["legacy_content_equal"] is not True
                or any(c[key] != p["full_v4_content_digest"] for key in ("pre_full_v4_content_digest", "post_full_v4_content_digest"))
                or any(c[key] != p["v5_migration_receipt_digest"] for key in ("pre_v5_migration_receipt_digest", "post_v5_migration_receipt_digest"))
                or any(c[key] != current["legacy_content_digest"] for key in ("pre_v4_legacy_content_digest", "post_v4_legacy_content_digest"))):
            raise ExecutiveSchemaUpgradeError("recovered completion current exact-v6 differs")
        alias_identity = _pre_census_alias_identity()
        def check():
            if _pre_census_alias_identity() != alias_identity:
                raise ExecutiveSchemaUpgradeError("recovered completion fixed alias changed")
            for obs in held: obs.check()
            for path, fd, origin in backups:
                if _pre_census_database_origin(path, fd, uid, gid) != origin:
                    raise ExecutiveSchemaUpgradeError("recovered completion immutable backup changed")
            _pre_census_prove_original_tool(q["original_tool"])
        check()
        yield check
        check()


def upgrade_v6_to_v7(
    database_path: str | Path,
    backup_directory: str | Path,
    *,
    release_sha: str,
) -> SchemaUpgradeV6ToV7Receipt:
    """Perform only the explicit offline exact-v6 to v7 transition.

    Reuses the incumbent installed-release proof, canonical offline service lock,
    quarantine barrier, stable writer census, checkpoint, source backup/drill,
    immutable receipts, exclusive SQLite transaction and custody revalidation.
    Only the reviewed physical-resource DDL executes. Every prior v6 cell and
    migration timestamp is conserved; all new physical tables begin empty.
    Preexisting physical Events refuse. No policy, caller or provider is armed.
    """

    release = _prove_upgrade_release(release_sha)
    candidate = Path(database_path).expanduser()
    _assert_private_regular_file(candidate, label="Executive exact-v6 database")
    database = candidate.resolve(strict=True)
    state_directory = database.parent
    marker = state_directory / DEFAULT_SERVICE_MARKER_NAME
    lock = state_directory / DEFAULT_SERVICE_LOCK_NAME
    barrier = state_directory / _UPGRADE_BARRIER_NAME
    preflight_path = state_directory / _UPGRADE_V6_TO_V7_PREFLIGHT_NAME
    completion_path = state_directory / _UPGRADE_V6_TO_V7_COMPLETION_NAME
    if any(os.path.lexists(path) for path in (barrier, preflight_path, completion_path)):
        raise ExecutiveSchemaUpgradeError(
            "v6-to-v7 upgrade barrier/receipt already exists; explicit operator "
            "reconciliation required before another attempt"
        )
    operation_id = uuid4().hex
    created_at = _upgrade_now()
    barrier_payload = {
        "schema_version": UPGRADE_BARRIER_SCHEMA,
        "operation_id": operation_id,
        "database_path": str(database),
        "tool_release_root": release["release_root"],
        "tool_release_tree_sha": release["release_tree_sha"],
        "tool_release_manifest_sha256": release["release_manifest_sha256"],
        "release_sha": release["release_sha"],
        "control_uid": os.geteuid(),
        "created_at": created_at,
    }
    before: dict[str, Any] | None = None
    preflight: dict[str, Any] | None = None
    barrier_identity: dict[str, Any] | None = None
    preflight_identity: dict[str, Any] | None = None
    census: dict[str, Any] | None = None
    committed_v7 = False
    with _offline_restore_lock(lock, marker, require_existing=True) as lock_fd, \
            _completed_pre_census_recovery(database, Path(backup_directory), release) as recovered_check:
        lock_identity = _held_service_lock_identity(lock, lock_fd)
        _write_private_json(barrier, barrier_payload)
        barrier_identity = _artifact_identity(
            barrier, expected_payload=barrier_payload
        )
        try:
            _upgrade_hook("barrier_persisted")
            _artifact_identity(
                barrier,
                expected_payload=barrier_payload,
                expected=barrier_identity,
            )
            if _marker_exists(marker):
                raise RestoreSafetyError("Executive service marker appeared before census")
            census = _upgrade_census(database, lock, barrier, lock_fd)
            _checkpoint_quiesced_wal(database)
            if _upgrade_census(database, lock, barrier, lock_fd) != census:
                raise RestoreSafetyError("writer census changed across WAL checkpoint")
            before = _upgrade_database_state(database, version=6)
            with _readonly_database(database) as connection:
                _require_no_physical_events(connection)
            v6_backup = create_offline_backup(
                database, backup_directory, expected_schema_version=6
            )
            _require_retained_backup_sidecar_absence(v6_backup.database_path)
            v6_drill = verify_restore_drill(
                v6_backup.database_path,
                v6_backup.manifest_path,
                expected_schema_version=6,
            )
            with _readonly_database(Path(v6_backup.database_path)) as connection:
                backup_full_v6 = full_v6_content_digest(connection)
            _require_retained_backup_sidecar_absence(v6_backup.database_path)
            if (
                v6_backup.legacy_content_digest != before["legacy_content_digest"]
                or v6_drill.legacy_content_digest != before["legacy_content_digest"]
                or v6_backup.normalized_schema_digest
                != before["normalized_schema_digest"]
                or v6_drill.normalized_schema_digest
                != before["normalized_schema_digest"]
                or backup_full_v6 != before["full_v6_content_digest"]
            ):
                raise ExecutiveSchemaUpgradeError("v6 source/backup/drill proof differs")
            preflight = {
                "schema_version": UPGRADE_PREFLIGHT_SCHEMA,
                "operation_id": operation_id,
                "source_schema_version": 6,
                "target_schema_version": 7,
                "database": before["database"],
                "migration_vector": before["migration_vector"],
                "normalized_schema_digest": before["normalized_schema_digest"],
                "full_v6_content_digest": before["full_v6_content_digest"],
                "barrier_identity": barrier_identity,
                "v6_backup": {
                    "database_path": v6_backup.database_path,
                    "database_sha256": v6_backup.database_sha256,
                    "manifest_path": v6_backup.manifest_path,
                    "manifest_sha256": v6_backup.manifest_sha256,
                    "restore_drill_receipt": v6_drill.to_dict(),
                    "restore_drill_digest": _upgrade_digest(v6_drill.to_dict()),
                    "full_v6_content_digest": backup_full_v6,
                },
                "quiesce_writer_census": census,
                "quiesce_writer_census_digest": _upgrade_digest(census),
                "tool_release_root": release["release_root"],
                "tool_release_tree_sha": release["release_tree_sha"],
                "tool_release_manifest_sha256": release[
                    "release_manifest_sha256"
                ],
                "release_sha": release["release_sha"],
                "created_at": created_at,
            }
            _write_private_json(preflight_path, preflight)
            preflight_identity = _artifact_identity(
                preflight_path, expected_payload=preflight
            )
            preflight_digest = _upgrade_digest(preflight)
            _upgrade_hook("preflight_persisted")

            def revalidate_control_artifacts() -> None:
                if recovered_check is not None:
                    recovered_check()
                if _marker_exists(marker):
                    raise RestoreSafetyError(
                        "Executive service marker appeared during schema upgrade"
                    )
                _held_service_lock_identity(lock, lock_fd, lock_identity)
                _artifact_identity(
                    barrier,
                    expected_payload=barrier_payload,
                    expected=barrier_identity,
                )
                _artifact_identity(
                    preflight_path,
                    expected_payload=preflight,
                    expected=preflight_identity,
                )
                if _prove_upgrade_release(release_sha) != release:
                    raise ExecutiveSchemaUpgradeError("tool release identity changed")
                _assert_upgrade_database_inode(database, before)

            def revalidate_v6_backup_proof() -> None:
                _require_retained_backup_sidecar_absence(v6_backup.database_path)
                checked = verify_backup(
                    v6_backup.database_path,
                    v6_backup.manifest_path,
                    expected_schema_version=6,
                )
                checked_drill = verify_restore_drill(
                    v6_backup.database_path,
                    v6_backup.manifest_path,
                    expected_schema_version=6,
                )
                with _readonly_database(Path(v6_backup.database_path)) as connection:
                    checked_full_v6 = full_v6_content_digest(connection)
                _require_retained_backup_sidecar_absence(v6_backup.database_path)
                if (
                    checked.database_sha256 != v6_backup.database_sha256
                    or checked.manifest_sha256 != v6_backup.manifest_sha256
                    or checked.normalized_schema_digest
                    != v6_backup.normalized_schema_digest
                    or checked.legacy_content_digest
                    != v6_backup.legacy_content_digest
                    or checked_full_v6 != backup_full_v6
                    or checked_drill.to_dict() != v6_drill.to_dict()
                    or _upgrade_digest(checked_drill.to_dict())
                    != preflight["v6_backup"]["restore_drill_digest"]
                ):
                    raise ExecutiveSchemaUpgradeError(
                        "v6 backup or restore-drill proof changed after preflight"
                    )

            revalidate_control_artifacts()
            revalidate_v6_backup_proof()
            if _upgrade_database_state(database, version=6) != before:
                raise ExecutiveSchemaUpgradeError("v6 source changed after preflight")
            if _upgrade_census(database, lock, barrier, lock_fd) != census:
                raise RestoreSafetyError("writer census changed before migration")

            connection = sqlite3.connect(database, isolation_level=None, timeout=5.0)
            connection.row_factory = sqlite3.Row
            try:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("BEGIN EXCLUSIVE")
                revalidate_control_artifacts()
                _verify_connection(connection, expected_schema_version=6)
                _require_no_physical_events(connection)
                if full_v6_content_digest(
                    connection
                ) != before["full_v6_content_digest"]:
                    raise ExecutiveSchemaUpgradeError("in-transaction v6 content changed")
                _upgrade_hook("exclusive_v6_verified")
                revalidate_control_artifacts()
                version, name, statements = _MIGRATIONS[6]
                if version != 7:
                    raise ExecutiveSchemaUpgradeError("reviewed migration 7 is unavailable")
                for ordinal, statement in enumerate(statements, 1):
                    connection.execute(statement)
                    _upgrade_hook(f"after_m7_statement:{ordinal:02d}")
                    revalidate_control_artifacts()
                connection.execute(
                    """
                    INSERT INTO schema_migrations(version,name,checksum,applied_at_ms)
                    VALUES(?,?,?,?)
                    """,
                    (
                        version,
                        name,
                        _migration_checksum(statements),
                        int(datetime.now(UTC).timestamp() * 1000),
                    ),
                )
                _upgrade_hook("after_m7_receipt")
                revalidate_control_artifacts()
                _verify_connection(connection, expected_schema_version=7)
                initial_physical_history = _require_initial_physical_history(connection)
                if full_v6_content_digest(
                    connection
                ) != before["full_v6_content_digest"]:
                    raise ExecutiveSchemaUpgradeError("migration changed full v6 content")
                _upgrade_hook("before_v7_commit")
                revalidate_control_artifacts()
                _verify_connection(connection, expected_schema_version=7)
                if _require_initial_physical_history(connection) != initial_physical_history:
                    raise ExecutiveSchemaUpgradeError("precommit physical history drifted")
                if full_v6_content_digest(
                    connection
                ) != before["full_v6_content_digest"]:
                    raise ExecutiveSchemaUpgradeError("precommit full v6 content drifted")
                connection.commit()
                committed_v7 = True
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()

            _upgrade_hook("after_v7_commit_before_checkpoint")
            revalidate_control_artifacts()
            _checkpoint_quiesced_wal(database)
            _upgrade_hook("after_v7_checkpoint")
            revalidate_control_artifacts()
            verified_v7 = _upgrade_database_state(database, version=7)
            if verified_v7["legacy_content_digest"] != before["legacy_content_digest"]:
                raise ExecutiveSchemaUpgradeError("committed v7 legacy content differs")
            with _readonly_database(database) as connection:
                committed_full_v6 = full_v6_content_digest(connection)
                committed_physical_history = _require_initial_physical_history(connection)
            if (committed_full_v6 != before["full_v6_content_digest"]
                    or committed_physical_history != initial_physical_history
                    or verified_v7["physical_history_digest"] != initial_physical_history):
                raise ExecutiveSchemaUpgradeError("committed v7 full v6 content differs")
            v7_backup = create_offline_backup(
                database, backup_directory, expected_schema_version=7
            )
            _require_retained_backup_sidecar_absence(v7_backup.database_path)
            v7_drill = verify_restore_drill(
                v7_backup.database_path,
                v7_backup.manifest_path,
                expected_schema_version=7,
            )
            with _readonly_database(Path(v7_backup.database_path)) as connection:
                v7_backup_full_v6 = full_v6_content_digest(connection)
                v7_backup_physical_history = _require_initial_physical_history(connection)
            _require_retained_backup_sidecar_absence(v7_backup.database_path)
            if (
                v7_backup.legacy_content_digest != before["legacy_content_digest"]
                or v7_drill.legacy_content_digest != before["legacy_content_digest"]
                or v7_backup.normalized_schema_digest
                != verified_v7["normalized_schema_digest"]
                or v7_drill.normalized_schema_digest
                != verified_v7["normalized_schema_digest"]
                or v7_backup_full_v6 != before["full_v6_content_digest"]
                or v7_backup_physical_history != initial_physical_history
            ):
                raise ExecutiveSchemaUpgradeError("v7 source/backup/drill proof differs")
            if _upgrade_census(database, lock, barrier, lock_fd) != census:
                raise RestoreSafetyError("writer census changed before completion")
            revalidate_control_artifacts()
            completed_at = _upgrade_now()
            completion = {
                "schema_version": UPGRADE_COMPLETION_SCHEMA,
                "operation_id": operation_id,
                "source_schema_version": 6,
                "target_schema_version": 7,
                "preflight_receipt_digest": preflight_digest,
                "authoritative_v7_database": verified_v7["database"],
                "authoritative_v7_schema_digest": verified_v7[
                    "normalized_schema_digest"
                ],
                "migration_vector": verified_v7["migration_vector"],
                "pre_full_v6_content_digest": before["full_v6_content_digest"],
                "post_full_v6_content_digest": committed_full_v6,
                "full_v6_content_equal": True,
                "physical_history_digest": initial_physical_history,
                "initial_physical_tables_empty": True,
                "pre_v6_legacy_content_digest": before["legacy_content_digest"],
                "post_v6_legacy_content_digest": verified_v7[
                    "legacy_content_digest"
                ],
                "legacy_content_equal": True,
                "v7_backup": {
                    "database_path": v7_backup.database_path,
                    "database_sha256": v7_backup.database_sha256,
                    "manifest_path": v7_backup.manifest_path,
                    "manifest_sha256": v7_backup.manifest_sha256,
                    "restore_drill_receipt": v7_drill.to_dict(),
                    "restore_drill_digest": _upgrade_digest(v7_drill.to_dict()),
                    "full_v6_content_digest": v7_backup_full_v6,
                    "physical_history_digest": v7_backup_physical_history,
                },
                "quiesce_writer_census_digest": _upgrade_digest(census),
                "tool_release_root": release["release_root"],
                "tool_release_tree_sha": release["release_tree_sha"],
                "tool_release_manifest_sha256": release[
                    "release_manifest_sha256"
                ],
                "release_sha": release["release_sha"],
                "completed_at": completed_at,
            }
            _write_private_json(completion_path, completion)
            completion_identity = _artifact_identity(
                completion_path, expected_payload=completion
            )
            _upgrade_hook("completion_persisted")
            # The final adversarial seam is deliberately placed before the
            # complete authoritative/backup/drill/census proof.  Nothing after
            # this hook may escape revalidation before the barrier is removed.
            _upgrade_hook("before_barrier_unlink")
            revalidate_control_artifacts()
            _artifact_identity(
                completion_path,
                expected_payload=completion,
                expected=completion_identity,
            )
            final_v7 = _upgrade_database_state(database, version=7)
            _require_retained_backup_sidecar_absence(v7_backup.database_path)
            final_v7_backup = verify_backup(
                v7_backup.database_path,
                v7_backup.manifest_path,
                expected_schema_version=7,
            )
            final_v7_drill = verify_restore_drill(
                v7_backup.database_path,
                v7_backup.manifest_path,
                expected_schema_version=7,
            )
            _require_retained_backup_sidecar_absence(v7_backup.database_path)
            with _readonly_database(database) as connection:
                final_full_v6 = full_v6_content_digest(connection)
                final_physical_history = _require_initial_physical_history(connection)
            if (
                final_v7 != verified_v7
                or final_full_v6 != before["full_v6_content_digest"]
                or final_physical_history != initial_physical_history
                or final_v7_backup.database_sha256 != v7_backup.database_sha256
                or final_v7_backup.manifest_sha256 != v7_backup.manifest_sha256
                or final_v7_backup.normalized_schema_digest
                != v7_backup.normalized_schema_digest
                or final_v7_backup.legacy_content_digest
                != v7_backup.legacy_content_digest
                or final_v7_drill.to_dict() != v7_drill.to_dict()
                or _upgrade_digest(final_v7_drill.to_dict())
                != completion["v7_backup"]["restore_drill_digest"]
            ):
                raise ExecutiveSchemaUpgradeError(
                    "completion v7 source/backup/drill proof changed"
                )
            # The retained source backup stays in custody after the commit, so
            # it is revalidated beside the final v7 proof before release.
            revalidate_v6_backup_proof()
            if _upgrade_census(database, lock, barrier, lock_fd) != census:
                raise RestoreSafetyError("writer census changed before barrier release")
            revalidate_control_artifacts()
            _artifact_identity(
                completion_path,
                expected_payload=completion,
                expected=completion_identity,
            )
            _unlink_exact_upgrade_artifact(
                barrier,
                expected_payload=barrier_payload,
                expected=barrier_identity,
            )
            return SchemaUpgradeV6ToV7Receipt(
                schema_version=UPGRADE_COMPLETION_SCHEMA,
                database_path=str(database),
                database_identity=dict(verified_v7["database"]),
                release_sha=release["release_sha"],
                preflight_receipt_path=str(preflight_path),
                preflight_receipt_digest=preflight_digest,
                completion_receipt_path=str(completion_path),
                completion_receipt_digest=_upgrade_digest(completion),
                source_schema_version=6,
                target_schema_version=7,
                pre_full_v6_content_digest=before["full_v6_content_digest"],
                post_full_v6_content_digest=committed_full_v6,
                full_v6_content_equal=True,
                physical_history_digest=initial_physical_history,
                v6_backup_path=v6_backup.database_path,
                v6_backup_manifest_path=v6_backup.manifest_path,
                v7_backup_path=v7_backup.database_path,
                v7_backup_manifest_path=v7_backup.manifest_path,
                completed_at=completed_at,
            )
        except Exception as exc:
            if committed_v7:
                _ensure_upgrade_quarantine_barrier(barrier, barrier_payload)
                raise ExecutiveSchemaUpgradeError(
                    "v7 committed but completion failed; barrier remains for forward fix"
                ) from exc
            if before is None or barrier_identity is None or census is None:
                _ensure_upgrade_quarantine_barrier(barrier, barrier_payload)
                raise ExecutiveSchemaUpgradeError(
                    "precommit upgrade failed before exact rollback proof; barrier remains"
                ) from exc
            try:
                _upgrade_hook("after_precommit_rollback_before_guard")
                current = _upgrade_database_state(database, version=6)
                if not _rollback_reproduces_preflight(current, before):
                    raise ExecutiveSchemaUpgradeError(
                        "rolled-back v6 state differs from frozen preflight"
                    )
                if _prove_upgrade_release(release_sha) != release:
                    raise ExecutiveSchemaUpgradeError(
                        "tool release identity changed before rollback cleanup"
                    )
                if _upgrade_census(database, lock, barrier, lock_fd) != census:
                    raise RestoreSafetyError(
                        "writer census changed before rollback barrier release"
                    )
                if _marker_exists(marker):
                    raise RestoreSafetyError(
                        "Executive service marker appeared before rollback cleanup"
                    )
                _held_service_lock_identity(lock, lock_fd, lock_identity)
                _artifact_identity(
                    barrier,
                    expected_payload=barrier_payload,
                    expected=barrier_identity,
                )
                if preflight is not None and preflight_identity is not None:
                    _artifact_identity(
                        preflight_path,
                        expected_payload=preflight,
                        expected=preflight_identity,
                    )
                    _unlink_exact_upgrade_artifact(
                        preflight_path,
                        expected_payload=preflight,
                        expected=preflight_identity,
                    )
                _unlink_exact_upgrade_artifact(
                    barrier,
                    expected_payload=barrier_payload,
                    expected=barrier_identity,
                )
            except Exception as guard_exc:
                _ensure_upgrade_quarantine_barrier(barrier, barrier_payload)
                raise ExecutiveSchemaUpgradeError(
                    "v6 rollback did not reproduce preflight; barrier remains"
                ) from guard_exc
            raise ExecutiveSchemaUpgradeError(
                f"v6 migration rolled back without v7 commit: {type(exc).__name__}: {exc}"
            ) from exc


__all__ = [
    "BACKUP_MANIFEST_SCHEMA_VERSION",
    "DEFAULT_SERVICE_LOCK_NAME",
    "DEFAULT_SERVICE_MARKER_NAME",
    "FULL_V4_CONTENT_PROJECTION_SCHEMA",
    "FULL_V5_CONTENT_PROJECTION_SCHEMA",
    "PHYSICAL_HISTORY_PROJECTION_SCHEMA",
    "BackupReceipt",
    "BackupVerification",
    "BackupVerificationError",
    "ExecutiveBackupError",
    "ExecutiveSchemaUpgradeError",
    "MigrationReceipt",
    "RestoreDrillReceipt",
    "RestoreReceipt",
    "RestoreRollbackError",
    "RestoreSafetyError",
    "SchemaUpgradeReceipt",
    "SchemaUpgradeV4ToV5Receipt",
    "SchemaUpgradeV5ToV6Receipt",
    "SchemaUpgradeV6ToV7Receipt",
    "create_offline_backup",
    "create_online_backup",
    "full_v4_content_digest",
    "full_v4_content_projection",
    "full_v5_content_digest",
    "full_v6_content_projection",
    "full_v6_content_digest",
    "full_v5_content_projection",
    "legacy_content_digest",
    "legacy_content_projection",
    "normalized_schema_digest",
    "physical_history_digest",
    "physical_history_projection",
    "restore_backup_offline",
    "upgrade_v3_to_v4",
    "upgrade_v4_to_v5",
    "upgrade_v5_to_v6",
    "upgrade_v6_to_v7",
    "verify_backup",
    "verify_restore_drill",
]
