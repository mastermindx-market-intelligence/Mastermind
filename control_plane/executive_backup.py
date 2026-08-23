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
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote
from uuid import uuid4

from control_plane.executive_runtime import (
    _MIGRATIONS,
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
}

UPGRADE_BARRIER_SCHEMA = "mastermind.executive_schema_upgrade_barrier/v1"
UPGRADE_PREFLIGHT_SCHEMA = "mastermind.executive_schema_upgrade_preflight/v1"
UPGRADE_COMPLETION_SCHEMA = "mastermind.executive_schema_upgrade_completion/v1"
UPGRADE_CENSUS_SCHEMA = "mastermind.executive_schema_upgrade_quiesce/v1"
_UPGRADE_BARRIER_NAME = "executive-schema-upgrade.in-progress.json"
_UPGRADE_PREFLIGHT_NAME = "executive-schema-upgrade.preflight.json"
_UPGRADE_COMPLETION_NAME = "executive-schema-upgrade.completion.json"
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
    if type(value) is not int or value not in {3, 4}:
        raise BackupVerificationError("expected schema version must be exactly 3 or 4")
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
    """Return the closed v1-v3 logical projection from exact v3 or v4."""

    expected_schema_version = _closed_schema_version(expected_schema_version)
    tables: list[dict[str, Any]] = []
    for name, columns, primary_key in _LEGACY_TABLE_COLUMNS:
        actual_columns = tuple(
            str(row[1]) for row in connection.execute(f'PRAGMA table_info("{name}")')
        )
        expected_columns = columns
        if expected_schema_version == 4 and name == "jobs":
            expected_columns = (*columns, *_V4_JOB_COLUMNS)
        elif expected_schema_version == 4 and name == "attempts":
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
    """Copy one quiesced exact-v3/v4 database without constructing RuntimeStore."""

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


def restore_backup_offline(
    store: RuntimeStore,
    database_path: str | Path,
    manifest_path: str | Path,
    *,
    service_marker_path: str | Path | None = None,
    service_lock_path: str | Path | None = None,
) -> RestoreReceipt:
    """Atomically restore a verified backup while the Executive service is offline.

    The service marker must be absent and the service advisory lock must be
    acquirable.  The prior main database and sidecars remain beside the restored
    database under the returned rollback path after success.
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

    target_candidate = store.path.expanduser()
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
    runtime_directory = _ensure_private_directory(target.parent)
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
    # Always hold the canonical lock.  The schema upgrader uses the same inode,
    # so it cannot create its barrier between our last check and the live swap.
    with _offline_restore_lock(lock, marker):
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
                raise BackupVerificationError(
                    "staged restore differs from the verified backup"
                )
            # TX-9 is deliberately applied to the staged copy, before any live
            # filename changes.  A controller crash can therefore leave either
            # the old authority or an already-invalidated replacement, never a
            # raw restored OHF writer authority at the live path.
            staged_store = RuntimeStore(
                store.root,
                busy_timeout_ms=store.busy_timeout_ms,
                database_path=staged,
            )
            invalidated = Runtime.from_store(
                staged_store
            ).operator_harness.invalidate_after_restore()
            final_staged = _verify_database_file(staged)
            copied_rollback = _preserve_rollback_set(target, rollback)
            if _marker_exists(marker):
                raise RestoreSafetyError(
                    "Executive service marker appeared before database replacement"
                )
            if os.path.lexists(canonical_upgrade_barrier):
                raise RestoreSafetyError(
                    "Executive schema upgrade barrier appeared before database replacement"
                )
            # From this point onward any failure must restore the rollback set.
            # Removing a WAL/SHM/journal mutates durable state even if the main
            # database os.replace() has not happened yet.
            live_mutated = True
            for suffix in _SIDECAR_SUFFIXES:
                try:
                    _sidecar(target, suffix).unlink()
                except FileNotFoundError:
                    pass
            os.replace(staged, target)
            target.chmod(0o600)
            _fsync_directory(runtime_directory)
            restored = _verify_database_file(target)
            if restored.database_sha256 != final_staged.database_sha256:
                raise BackupVerificationError(
                    "restored database hash differs from staged invalidated runtime"
                )
            store._schema_ready = False
            return RestoreReceipt(
                restored_database_path=str(target),
                restored_sha256=restored.database_sha256,
                rollback_database_path=str(rollback),
                rollback_sidecar_paths=tuple(
                    str(path) for path in copied_rollback if path != rollback
                ),
                rollback_sha256=_sha256_path(rollback),
                manifest_sha256=verified.manifest_sha256,
                restored_at=_utc_now(),
                source_backup_sha256=verified.database_sha256,
                final_runtime_sha256=restored.database_sha256,
                ohf_invalidated_attempts=invalidated,
            )
        except Exception as exc:
            if live_mutated and rollback.exists():
                try:
                    _restore_rollback_set(target, rollback)
                    store._schema_ready = False
                    with _readonly_database(target) as rollback_connection:
                        _verify_connection(rollback_connection)
                except (OSError, sqlite3.Error, RuntimeProofError) as rollback_exc:
                    raise RestoreRollbackError(
                        f"restore failed and rollback also failed: {type(rollback_exc).__name__}: {rollback_exc}"
                    ) from exc
                raise RestoreRollbackError(
                    f"restore mutation failed; previous database bytes were restored: {type(exc).__name__}: {exc}"
                ) from exc
            for path in copied_rollback:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            raise
        finally:
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


def _default_upgrade_census(
    database: Path, lock: Path, barrier: Path, lock_fd: int
) -> Mapping[str, Any]:
    control_uids = sorted(
        set(
            os.getresuid()
            if hasattr(os, "getresuid")
            else (os.getuid(), os.geteuid())
        )
    )
    ps_status, ps_output, ps_error, ps_pid = _run_census_command(
        ["/bin/ps", "-axo", "pid=,svuid=,ruid=,uid=,command="]
    )
    if ps_status != 0 or ps_error:
        raise RestoreSafetyError("independent process census failed closed")
    process_rows: list[dict[str, Any]] = []
    upgrader_observed = False
    sensor_child_observed = False
    for line in ps_output.splitlines():
        parts = line.strip().split(None, 4)
        if len(parts) != 5 or any(not parts[index].isdigit() for index in range(4)):
            raise RestoreSafetyError("independent process census is malformed")
        pid = int(parts[0])
        observed_uids = {int(parts[1]), int(parts[2]), int(parts[3])}
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
    status, output, error, _lsof_pid = _run_census_command(
        [str(lsof), "-nP", "-F", "pufn", "--", *existing]
    )
    if status != 0 or error:
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
    if len(file_rows) != 1:
        raise RestoreSafetyError(
            "independent file census omitted or duplicated the held lock sentinel"
        )
    allowed_fd = re.fullmatch(r"[0-9]+", str(lock_fd))
    for row in file_rows:
        fd_number = re.match(r"[0-9]+", str(row["fd"]))
        if (
            row["pid"] != os.getpid()
            or row["uid"] != os.geteuid()
            or row["path"] != str(lock)
            or fd_number is None
            or allowed_fd is None
            or int(fd_number.group()) != lock_fd
        ):
            raise RestoreSafetyError("independent file census found another open runtime file")
        # lsof decorates descriptors with access-mode suffixes (for example
        # ``3u``).  Persist the closed numeric identity used by repeated census
        # comparison rather than a presentation detail of the sensor.
        row["fd"] = str(lock_fd)
    return {
        "schema_version": UPGRADE_CENSUS_SCHEMA,
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
        material["schema_version"] != UPGRADE_CENSUS_SCHEMA
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
        or material["open_files"]
        != [
            {
                "pid": os.getpid(),
                "uid": os.geteuid(),
                "fd": str(lock_fd),
                "path": str(lock),
            }
        ]
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
    return {
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


__all__ = [
    "BACKUP_MANIFEST_SCHEMA_VERSION",
    "DEFAULT_SERVICE_LOCK_NAME",
    "DEFAULT_SERVICE_MARKER_NAME",
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
    "create_offline_backup",
    "create_online_backup",
    "legacy_content_digest",
    "legacy_content_projection",
    "normalized_schema_digest",
    "restore_backup_offline",
    "upgrade_v3_to_v4",
    "verify_backup",
    "verify_restore_drill",
]
