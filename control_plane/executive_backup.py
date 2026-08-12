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
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from control_plane.executive_runtime import (
    _MIGRATIONS,
    SCHEMA_VERSION,
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


class ExecutiveBackupError(RuntimeProofError):
    """Base class for operator-visible Executive backup failures."""


class BackupVerificationError(ExecutiveBackupError):
    """A backup, manifest, or restored database failed closed verification."""


class RestoreSafetyError(ExecutiveBackupError):
    """An offline restore could not prove that the service was stopped."""


class RestoreRollbackError(ExecutiveBackupError):
    """A restore failed after replacement and the prior bytes were restored."""


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
        }


@dataclasses.dataclass(frozen=True)
class RestoreDrillReceipt:
    database_sha256: str
    runtime_schema_version: int
    migration_versions: tuple[int, ...]
    integrity_check: str = "ok"
    foreign_key_check: str = "ok"

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


def _expected_migrations() -> tuple[MigrationReceipt, ...]:
    return tuple(
        MigrationReceipt(
            version=int(version),
            name=str(name),
            checksum=hashlib.sha256(
                "\n".join(statement.strip() for statement in statements).encode("utf-8")
            ).hexdigest(),
        )
        for version, name, statements in _MIGRATIONS
    )


def _verify_connection(
    connection: sqlite3.Connection,
) -> tuple[int, int, tuple[MigrationReceipt, ...]]:
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
        expected = _expected_migrations()
        if actual != expected:
            raise BackupVerificationError(
                "database migrations do not exactly match the migrations known to this runtime"
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


def _verify_database_file(path: Path) -> BackupVerification:
    candidate = path.expanduser()
    _assert_private_regular_file(candidate, label="backup database")
    resolved = candidate.resolve(strict=True)
    info = _assert_private_regular_file(resolved, label="backup database")
    if info.st_size <= 0:
        raise BackupVerificationError("backup database is empty")
    database_hash = _sha256_path(resolved)
    with _readonly_database(resolved) as connection:
        page_count, page_size, migrations = _verify_connection(connection)
    return BackupVerification(
        database_path=str(resolved),
        database_sha256=database_hash,
        database_size=info.st_size,
        page_count=page_count,
        page_size=page_size,
        migrations=migrations,
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
) -> dict[str, Any]:
    return {
        "schema_version": BACKUP_MANIFEST_SCHEMA_VERSION,
        "backup_id": backup_id,
        "created_at": created_at,
        "runtime_schema_version": SCHEMA_VERSION,
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
) -> None:
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
    if manifest.get("runtime_schema_version") != SCHEMA_VERSION:
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


def verify_backup(
    database_path: str | Path,
    manifest_path: str | Path | None = None,
) -> BackupVerification:
    """Verify bytes, SQLite health, migration identity, and optional manifest."""

    verification = _verify_database_file(Path(database_path))
    database = Path(verification.database_path)
    if manifest_path is None:
        return verification
    manifest = Path(manifest_path).expanduser().resolve(strict=True)
    payload, manifest_hash = _load_manifest(manifest)
    _verify_manifest(payload, database_path=database, verification=verification)
    return dataclasses.replace(
        verification,
        manifest_path=str(manifest),
        manifest_sha256=manifest_hash,
    )


def verify_restore_drill(
    database_path: str | Path,
    manifest_path: str | Path | None = None,
) -> RestoreDrillReceipt:
    """Open a private isolated restored copy through ``RuntimeStore`` and discard it."""

    verified = verify_backup(database_path, manifest_path)
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
        restored_store = RuntimeStore(root)
        with restored_store.read() as connection:
            _page_count, _page_size, migrations = _verify_connection(connection)
        return RestoreDrillReceipt(
            database_sha256=verified.database_sha256,
            runtime_schema_version=SCHEMA_VERSION,
            migration_versions=tuple(item.version for item in migrations),
        )


def _marker_exists(path: Path) -> bool:
    return os.path.lexists(path)


@contextmanager
def _offline_restore_lock(path: Path, marker: Path) -> Iterator[None]:
    if _marker_exists(marker):
        raise RestoreSafetyError(
            f"Executive service marker exists; stop the service first: {marker}"
        )
    parent = _ensure_private_directory(path.parent)
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise RestoreSafetyError(f"cannot open Executive service lock: {exc}") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
            raise RestoreSafetyError(
                "Executive service lock is not an owner-controlled file"
            )
        if stat.S_IMODE(info.st_mode) & 0o077:
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
        yield
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
    runtime_directory = _ensure_private_directory(target.parent)
    marker = (
        Path(service_marker_path).expanduser().resolve(strict=False)
        if service_marker_path is not None
        else runtime_directory / DEFAULT_SERVICE_MARKER_NAME
    )
    lock = (
        Path(service_lock_path).expanduser().resolve(strict=False)
        if service_lock_path is not None
        else runtime_directory / DEFAULT_SERVICE_LOCK_NAME
    )
    if marker == lock:
        raise RestoreSafetyError("service marker and lock must be distinct paths")
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
    with _offline_restore_lock(lock, marker):
        try:
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
            copied_rollback = _preserve_rollback_set(target, rollback)
            if _marker_exists(marker):
                raise RestoreSafetyError(
                    "Executive service marker appeared before database replacement"
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
            if restored.database_sha256 != verified.database_sha256:
                raise BackupVerificationError(
                    "restored database hash differs from the verified backup"
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
            )
        except Exception as exc:
            if live_mutated and rollback.exists():
                try:
                    _restore_rollback_set(target, rollback)
                    store._schema_ready = False
                    with store.read() as rollback_connection:
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


__all__ = [
    "BACKUP_MANIFEST_SCHEMA_VERSION",
    "DEFAULT_SERVICE_LOCK_NAME",
    "DEFAULT_SERVICE_MARKER_NAME",
    "BackupReceipt",
    "BackupVerification",
    "BackupVerificationError",
    "ExecutiveBackupError",
    "MigrationReceipt",
    "RestoreDrillReceipt",
    "RestoreReceipt",
    "RestoreRollbackError",
    "RestoreSafetyError",
    "create_online_backup",
    "restore_backup_offline",
    "verify_backup",
    "verify_restore_drill",
]
