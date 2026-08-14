"""Archive a failed Phase 1C-A host proof so the exact SHA can be retried.

This is deliberately narrower than an uninstall.  It stops only the two fixed
Executive LaunchDaemons, terminates processes owned by the two dedicated
service UIDs, and atomically moves mutable proof state to a root-only archive.
Installed releases, policy, plists, the pinned runtimes, and worker auth are
never targets.
"""
from __future__ import annotations

import argparse
import grp
import hashlib
import json
import os
import pwd
import re
import secrets
import signal
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence


CONTROL_LABEL = "com.mastermind.executive.control"
WORKER_LABEL = "com.mastermind.executive.worker.codex"
CONTROL_USER = "_mastermind_exec"
CONTROL_GROUP = "_mastermind_exec"
WORKER_USER = "_mastermind_worker"
WORKER_GROUP = "_mastermind_worker"
SYSTEM_ROOT = Path("/Library/Application Support/MastermindExecutive")
RUNTIME_ROOT = Path("/var/db/mastermind-executive")
ARCHIVE_ROOT = Path("/var/db/mastermind-executive-acceptance-archive")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class RetryError(RuntimeError):
    """A safe retry preparation could not be completed."""


class RetryInterrupted(RetryError):
    """The operator interrupted retry preparation."""


@dataclass(frozen=True)
class HostLayout:
    system_root: Path = SYSTEM_ROOT
    runtime_root: Path = RUNTIME_ROOT
    archive_root: Path = ARCHIVE_ROOT


@dataclass(frozen=True)
class PrincipalIds:
    control_uid: int
    control_gid: int
    worker_uid: int
    worker_gid: int
    root_uid: int = 0
    wheel_gid: int = 0


@dataclass(frozen=True)
class ArchiveTarget:
    source: Path
    archive_name: str
    expected_kind: str


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _run(
    argv: Sequence[str | os.PathLike[str]],
    *,
    label: str,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(
        [os.fspath(value) for value in argv],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60.0,
    )
    if check and completed.returncode != 0:
        raise RetryError(f"{label} failed with exit {completed.returncode}")
    return completed


def _write_json_exclusive(path: Path, value: Any) -> None:
    payload = (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
        + "\n"
    ).encode("utf-8")
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o400,
    )
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short archive receipt write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _path_identity(path: Path) -> dict[str, int]:
    info = path.lstat()
    return {
        "device": info.st_dev,
        "inode": info.st_ino,
        "uid": info.st_uid,
        "gid": info.st_gid,
        "mode": stat.S_IMODE(info.st_mode),
        "size": info.st_size,
        "mtime_ns": info.st_mtime_ns,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _has_acl(path: Path) -> bool:
    if sys.platform != "darwin":
        return False
    completed = _run(
        ["/usr/bin/stat", "-f", "%Sp", path],
        label="filesystem ACL metadata check",
    )
    return "+" in completed.stdout.decode("ascii", errors="strict")


def _clear_acl(path: Path) -> None:
    if sys.platform == "darwin":
        _run(["/bin/chmod", "-N", path], label="clear inherited filesystem ACL")
        if _has_acl(path):
            raise RetryError("filesystem ACL remained after explicit removal")


def _inventory_tree(path: Path) -> dict[str, Any]:
    """Inventory archived bytes without following links or serializing contents."""

    entries: list[dict[str, Any]] = []

    def visit(current: Path, relative: Path) -> None:
        info = current.lstat()
        entry: dict[str, Any] = {
            "path": os.fspath(relative),
            "uid": info.st_uid,
            "gid": info.st_gid,
            "mode": stat.S_IMODE(info.st_mode),
            "size": info.st_size,
        }
        if stat.S_ISDIR(info.st_mode):
            entry["kind"] = "directory"
            entries.append(entry)
            for child in sorted(current.iterdir(), key=lambda item: os.fsencode(item.name)):
                visit(child, relative / child.name)
            return
        if stat.S_ISREG(info.st_mode):
            entry["kind"] = "file"
            entry["sha256"] = _sha256_file(current)
        elif stat.S_ISLNK(info.st_mode):
            entry["kind"] = "symlink"
            entry["target_sha256"] = hashlib.sha256(os.fsencode(os.readlink(current))).hexdigest()
        else:
            entry["kind"] = "special"
        entries.append(entry)

    visit(path, Path(path.name))
    encoded = json.dumps(
        entries,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return {
        "entry_count": len(entries),
        "inventory_sha256": hashlib.sha256(encoded).hexdigest(),
        "entries": entries,
    }


class AcceptanceRetry:
    def __init__(
        self,
        *,
        expected_sha: str,
        release: Path,
        layout: HostLayout,
        principals: PrincipalIds,
    ) -> None:
        self.expected_sha = expected_sha
        self.release = release
        self.layout = layout
        self.principals = principals
        self.archive_path: Path | None = None
        self.moved: list[dict[str, Any]] = []

    @property
    def provider_auth(self) -> Path:
        return (
            self.layout.runtime_root
            / "workers"
            / "codex-01"
            / "provider-home"
            / "auth.json"
        )

    def archive_targets(self) -> tuple[ArchiveTarget, ...]:
        runtime = self.layout.runtime_root
        return (
            ArchiveTarget(runtime / "control" / "db", "control-db", "directory"),
            ArchiveTarget(
                runtime / "control" / "launch-receipts",
                "launch-receipts",
                "directory",
            ),
            ArchiveTarget(runtime / "control" / "backups", "backups", "directory"),
            ArchiveTarget(runtime / "control" / "canaries", "canaries", "directory"),
            ArchiveTarget(
                runtime / "control" / "acceptance" / self.expected_sha,
                "acceptance-receipts",
                "directory",
            ),
            ArchiveTarget(runtime / "jobs" / "workspaces", "workspaces", "directory"),
            ArchiveTarget(runtime / "jobs" / "runs", "runs", "directory"),
            ArchiveTarget(runtime / "canary-fixtures", "canary-fixtures", "directory"),
            ArchiveTarget(
                runtime / "workers" / "codex-01" / "state",
                "worker-state",
                "directory",
            ),
            ArchiveTarget(
                runtime
                / "control"
                / "admin-checkout"
                / self.expected_sha
                / ".git"
                / "executive-secret-canary",
                "administrative-checkout-sentinel",
                "file",
            ),
        )

    def _active_directory_specs(self) -> tuple[tuple[Path, int, int, int], ...]:
        runtime = self.layout.runtime_root
        ids = self.principals
        return (
            (runtime / "control" / "db", ids.control_uid, ids.control_gid, 0o700),
            (
                runtime / "control" / "launch-receipts",
                ids.control_uid,
                ids.control_gid,
                0o700,
            ),
            (runtime / "control" / "backups", ids.control_uid, ids.control_gid, 0o700),
            (runtime / "control" / "canaries", ids.control_uid, ids.control_gid, 0o700),
            (
                runtime / "control" / "acceptance",
                ids.control_uid,
                ids.control_gid,
                0o700,
            ),
            (runtime / "jobs" / "workspaces", ids.control_uid, ids.worker_gid, 0o710),
            (runtime / "jobs" / "runs", ids.control_uid, ids.worker_gid, 0o710),
            (
                runtime / "workers" / "codex-01" / "state",
                ids.worker_uid,
                ids.worker_gid,
                0o700,
            ),
            (runtime / "canary-fixtures", ids.control_uid, ids.control_gid, 0o700),
            (
                runtime / "canary-fixtures" / "other-worker-home",
                ids.control_uid,
                ids.control_gid,
                0o700,
            ),
            (
                runtime / "canary-fixtures" / "production-like",
                ids.control_uid,
                ids.control_gid,
                0o700,
            ),
        )

    def validate_host(self) -> None:
        if os.geteuid() != 0 or sys.platform != "darwin":
            raise RetryError("acceptance retry preparation requires root on macOS")
        if _SHA_RE.fullmatch(self.expected_sha) is None:
            raise RetryError("expected SHA must be exactly 40 lowercase hexadecimal characters")
        release_entry = self.layout.system_root / "releases" / self.expected_sha
        release_info = release_entry.lstat()
        if (
            stat.S_ISLNK(release_info.st_mode)
            or not stat.S_ISDIR(release_info.st_mode)
            or release_info.st_uid != self.principals.root_uid
            or release_info.st_gid != self.principals.wheel_gid
            or stat.S_IMODE(release_info.st_mode) & 0o022
            or _has_acl(release_entry)
        ):
            raise RetryError("installed release root is missing or unsafe")
        expected_release = release_entry.resolve(strict=True)
        if self.release.resolve(strict=True) != expected_release:
            raise RetryError("retry helper is not running from the expected installed release")
        runtime_info = self.layout.runtime_root.lstat()
        if (
            stat.S_ISLNK(runtime_info.st_mode)
            or not stat.S_ISDIR(runtime_info.st_mode)
            or runtime_info.st_uid != self.principals.root_uid
            or runtime_info.st_gid != self.principals.wheel_gid
            or stat.S_IMODE(runtime_info.st_mode) != 0o711
            or _has_acl(self.layout.runtime_root)
        ):
            raise RetryError("Executive runtime root is missing or unsafe")
        if self.principals.control_uid == self.principals.worker_uid:
            raise RetryError("control and worker service UIDs are not distinct")
        service_control = self.release / "ops" / "executive_os" / "service-control.sh"
        info = service_control.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_uid != self.principals.root_uid
            or info.st_gid != self.principals.wheel_gid
            or stat.S_IMODE(info.st_mode) & 0o022
            or _has_acl(service_control)
        ):
            raise RetryError("installed service controller is missing or unsafe")
        provider_home = self.provider_auth.parent
        provider_info = provider_home.lstat()
        if (
            stat.S_ISLNK(provider_info.st_mode)
            or not stat.S_ISDIR(provider_info.st_mode)
            or provider_info.st_uid != self.principals.worker_uid
            or provider_info.st_gid != self.principals.worker_gid
            or stat.S_IMODE(provider_info.st_mode) != 0o700
            or _has_acl(provider_home)
        ):
            raise RetryError("dedicated worker provider home metadata drifted")
        if not self.provider_auth.is_file() or self.provider_auth.is_symlink():
            raise RetryError("dedicated worker auth is unavailable; retry archive was not started")
        auth_info = self.provider_auth.lstat()
        if (
            auth_info.st_uid != self.principals.worker_uid
            or auth_info.st_gid != self.principals.worker_gid
            or stat.S_IMODE(auth_info.st_mode) != 0o600
            or auth_info.st_nlink != 1
            or _has_acl(self.provider_auth)
        ):
            raise RetryError("dedicated worker auth metadata drifted; retry archive was not started")

    def _preflight_archive_layout(self) -> None:
        ids = self.principals
        archive_parent = self.layout.archive_root.parent
        parent_info = archive_parent.lstat()
        if (
            stat.S_ISLNK(parent_info.st_mode)
            or not stat.S_ISDIR(parent_info.st_mode)
            or parent_info.st_uid != ids.root_uid
            or parent_info.st_gid != ids.wheel_gid
            or stat.S_IMODE(parent_info.st_mode) & 0o022
            or _has_acl(archive_parent)
        ):
            raise RetryError("acceptance archive parent is missing or unsafe")
        if archive_parent.stat().st_dev != self.layout.runtime_root.stat().st_dev:
            raise RetryError("acceptance archive must share a filesystem with runtime state")
        for directory in (
            self.layout.archive_root,
            self.layout.archive_root / self.expected_sha,
        ):
            if not directory.exists() and not directory.is_symlink():
                continue
            info = directory.lstat()
            if (
                stat.S_ISLNK(info.st_mode)
                or not stat.S_ISDIR(info.st_mode)
                or info.st_uid != ids.root_uid
                or info.st_gid != ids.wheel_gid
                or stat.S_IMODE(info.st_mode) != 0o700
                or _has_acl(directory)
            ):
                raise RetryError(f"unsafe acceptance archive directory: {directory}")
        for target in self.archive_targets():
            if not target.source.exists() and not target.source.is_symlink():
                continue
            info = target.source.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise RetryError(f"refusing to archive symlinked runtime target: {target.source}")
            if target.expected_kind == "directory" and not stat.S_ISDIR(info.st_mode):
                raise RetryError(f"runtime archive target is not a directory: {target.source}")
            if target.expected_kind == "file" and not stat.S_ISREG(info.st_mode):
                raise RetryError(f"runtime archive target is not a file: {target.source}")
            if _has_acl(target.source):
                raise RetryError(f"runtime archive target has a filesystem ACL: {target.source}")
            if target.archive_name == "acceptance-receipts" and (
                info.st_uid != ids.control_uid
                or info.st_gid != ids.control_gid
                or stat.S_IMODE(info.st_mode) != 0o700
            ):
                raise RetryError("acceptance receipt root metadata drifted")
            if target.archive_name == "administrative-checkout-sentinel" and (
                info.st_uid != ids.control_uid
                or info.st_gid != ids.control_gid
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1
            ):
                raise RetryError("administrative checkout sentinel metadata drifted")
        for path, _uid, _gid, _mode in self._active_directory_specs():
            if not path.exists() and not path.is_symlink():
                continue
            info = path.lstat()
            if (
                stat.S_ISLNK(info.st_mode)
                or not stat.S_ISDIR(info.st_mode)
                or info.st_uid != _uid
                or info.st_gid != _gid
                or stat.S_IMODE(info.st_mode) != _mode
                or _has_acl(path)
            ):
                raise RetryError(f"unsafe active runtime directory: {path}")

    def _protected_identities(self) -> dict[str, dict[str, int]]:
        return {
            "installed_release": _path_identity(self.release),
            "worker_auth": _path_identity(self.provider_auth),
        }

    def _assert_protected_unchanged(self, before: dict[str, dict[str, int]]) -> None:
        after = self._protected_identities()
        if after != before:
            raise RetryError("installed release or worker auth changed during retry preparation")

    def _stop_services(self) -> dict[str, Any]:
        service_control = self.release / "ops" / "executive_os" / "service-control.sh"
        results: dict[str, int] = {}
        completed = _run(
            ["/bin/bash", service_control, "stop"],
            label="bounded Executive service stop",
            check=False,
        )
        results["service_control_stop"] = completed.returncode
        for label in (CONTROL_LABEL, WORKER_LABEL):
            results[f"disable_{label}"] = _run(
                ["/bin/launchctl", "disable", f"system/{label}"],
                label=f"disable {label}",
                check=False,
            ).returncode
            results[f"bootout_{label}"] = _run(
                ["/bin/launchctl", "bootout", f"system/{label}"],
                label=f"bootout {label}",
                check=False,
            ).returncode
        for label in (CONTROL_LABEL, WORKER_LABEL):
            if _run(
                ["/bin/launchctl", "print", f"system/{label}"],
                label=f"verify {label} stopped",
                check=False,
            ).returncode == 0:
                raise RetryError(f"Executive service remained loaded after stop: {label}")
        return results

    @staticmethod
    def _uid_processes(uids: set[int]) -> dict[int, list[int]]:
        """Census every process a dedicated UID can still own.

        This is an independent quiescence proof from the broker's own sweep,
        and it runs as root immediately before the release is archived, so a
        false "quiescent" here archives state out from under a live worker.

        It matches the broker's projection deliberately: ``ps -o uid`` prints
        the EFFECTIVE uid, while the kernel's signal check uses the receiver's
        real or SAVED uid, so an effective-only census both misses processes
        the caller can signal and is not a superset of them.  The union of the
        saved, real, and effective columns can only over-report, which fails
        the retry closed instead of certifying a false absence.  Every parse
        refusal below is fail-closed for the same reason.
        """

        completed = _run(
            ["/bin/ps", "-axo", "svuid=,ruid=,uid=,pid="],
            label="dedicated service UID process census",
        )
        found: dict[int, list[int]] = {uid: [] for uid in uids}
        rows = 0
        for raw_line in completed.stdout.decode("ascii", errors="strict").splitlines():
            if not raw_line.strip():
                continue
            fields = raw_line.split()
            if len(fields) != 4:
                raise RetryError("dedicated service UID process census is malformed")
            try:
                saved_uid, real_uid, effective_uid, pid = (
                    int(value) for value in fields
                )
            except ValueError:
                raise RetryError(
                    "dedicated service UID process census is malformed"
                ) from None
            rows += 1
            if pid <= 1:
                continue
            for uid in (saved_uid, real_uid, effective_uid):
                if uid in found:
                    found[uid].append(pid)
        if rows == 0:
            raise RetryError("dedicated service UID process census is empty")
        return {uid: sorted(set(pids)) for uid, pids in found.items()}

    def _quiesce_dedicated_uids(self) -> dict[str, Any]:
        uids = {self.principals.control_uid, self.principals.worker_uid}
        before = self._uid_processes(uids)
        signals_sent: list[dict[str, int]] = []
        for signum, wait_seconds in ((signal.SIGTERM, 5.0), (signal.SIGKILL, 5.0)):
            deadline = time.monotonic() + wait_seconds
            while time.monotonic() < deadline:
                live = self._uid_processes(uids)
                pids = sorted({pid for values in live.values() for pid in values})
                if not pids:
                    break
                for pid in pids:
                    try:
                        os.kill(pid, signum)
                        signals_sent.append({"pid": pid, "signal": int(signum)})
                    except ProcessLookupError:
                        pass
                time.sleep(0.1)
        after = self._uid_processes(uids)
        if any(after.values()):
            raise RetryError("a dedicated Executive UID still owns a live process")
        return {
            "before": {str(uid): pids for uid, pids in sorted(before.items())},
            "after": {str(uid): pids for uid, pids in sorted(after.items())},
            "signals_sent": signals_sent,
            "passed": True,
        }

    def _create_archive_destination(self) -> Path:
        ids = self.principals
        for directory in (
            self.layout.archive_root,
            self.layout.archive_root / self.expected_sha,
        ):
            if directory.exists() or directory.is_symlink():
                info = directory.lstat()
                if (
                    stat.S_ISLNK(info.st_mode)
                    or not stat.S_ISDIR(info.st_mode)
                    or info.st_uid != ids.root_uid
                    or info.st_gid != ids.wheel_gid
                    or stat.S_IMODE(info.st_mode) != 0o700
                ):
                    raise RetryError(f"unsafe acceptance archive directory: {directory}")
            else:
                directory.mkdir(mode=0o700)
                _clear_acl(directory)
                os.chown(directory, ids.root_uid, ids.wheel_gid)
                os.chmod(directory, 0o700)
        if self.layout.archive_root.stat().st_dev != self.layout.runtime_root.stat().st_dev:
            raise RetryError("acceptance archive must share a filesystem with runtime state")
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + f"-{secrets.token_hex(4)}"
        destination = self.layout.archive_root / self.expected_sha / run_id
        destination.mkdir(mode=0o700)
        _clear_acl(destination)
        os.chown(destination, ids.root_uid, ids.wheel_gid)
        os.chmod(destination, 0o700)
        return destination

    def _archive_runtime(self, destination: Path) -> list[dict[str, Any]]:
        moved: list[dict[str, Any]] = []
        for target in self.archive_targets():
            if not target.source.exists() and not target.source.is_symlink():
                moved.append(
                    {
                        "source": os.fspath(target.source),
                        "archive_name": target.archive_name,
                        "status": "ABSENT",
                    }
                )
                continue
            info = target.source.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise RetryError(f"refusing to archive symlinked runtime target: {target.source}")
            if target.expected_kind == "directory" and not stat.S_ISDIR(info.st_mode):
                raise RetryError(f"runtime archive target is not a directory: {target.source}")
            if target.expected_kind == "file" and not stat.S_ISREG(info.st_mode):
                raise RetryError(f"runtime archive target is not a file: {target.source}")
            archived = destination / target.archive_name
            if archived.exists() or archived.is_symlink():
                raise RetryError(f"duplicate runtime archive target: {archived}")
            os.rename(target.source, archived)
            record: dict[str, Any] = {
                "source": os.fspath(target.source),
                "archive_name": target.archive_name,
                "status": "ARCHIVED_INVENTORY_PENDING",
            }
            moved.append(record)
            self.moved = list(moved)
            record.update(_inventory_tree(archived))
            record["status"] = "ARCHIVED"
            self.moved = list(moved)
        return moved

    def _ensure_active_directories(self) -> None:
        for path, uid, gid, mode in self._active_directory_specs():
            if path.exists() or path.is_symlink():
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                    raise RetryError(f"unsafe active runtime directory: {path}")
            else:
                path.mkdir(mode=mode)
                _clear_acl(path)
            os.chown(path, uid, gid)
            os.chmod(path, mode)
            if _has_acl(path):
                raise RetryError(f"active runtime directory retained an ACL: {path}")

    def _leave_stopped_and_recoverable(self) -> dict[str, Any]:
        errors: list[str] = []
        stop: dict[str, Any] = {}
        sweep: dict[str, Any] = {}
        try:
            stop = self._stop_services()
        except (OSError, RetryError, subprocess.TimeoutExpired) as exc:
            errors.append(f"stop: {type(exc).__name__}: {exc}")
        try:
            sweep = self._quiesce_dedicated_uids()
        except (OSError, RetryError, subprocess.TimeoutExpired) as exc:
            errors.append(f"UID sweep: {type(exc).__name__}: {exc}")
        try:
            self._ensure_active_directories()
        except (OSError, RetryError) as exc:
            errors.append(f"directory recovery: {type(exc).__name__}: {exc}")
        if errors:
            raise RetryError("; ".join(errors))
        return {"service_stop": stop, "uid_sweep": sweep, "passed": True}

    def _stop_and_quiesce(self) -> dict[str, Any]:
        return {
            "service_stop": self._stop_services(),
            "uid_sweep": self._quiesce_dedicated_uids(),
            "passed": True,
        }

    def _write_archive_receipt(self, name: str, value: Any) -> None:
        if self.archive_path is None:
            return
        _write_json_exclusive(self.archive_path / name, value)
        os.chown(
            self.archive_path / name,
            self.principals.root_uid,
            self.principals.wheel_gid,
        )
        os.chmod(self.archive_path / name, 0o400)
        _clear_acl(self.archive_path / name)

    def run(self) -> Path:
        self.validate_host()
        self._preflight_archive_layout()
        protected_before = self._protected_identities()
        self.archive_path = self._create_archive_destination()
        self._write_archive_receipt(
            "archive-start.json",
            {
                "schema_version": "mastermind.executive_acceptance_retry_archive/v1",
                "status": "PREPARED",
                "started_at": _now(),
                "expected_sha": self.expected_sha,
            },
        )
        primary_error: BaseException | None = None
        start_quiescence: dict[str, Any] | None = None
        final_quiescence: dict[str, Any] | None = None
        quiescence_started = False
        try:
            quiescence_started = True
            start_quiescence = self._stop_and_quiesce()
            self._write_archive_receipt(
                "archive-quiesced.json",
                {
                    "schema_version": "mastermind.executive_acceptance_retry_archive/v1",
                    "status": "QUIESCED",
                    "observed_at": _now(),
                    "expected_sha": self.expected_sha,
                    "start_quiescence": start_quiescence,
                },
            )
            self.moved = self._archive_runtime(self.archive_path)
        except BaseException as exc:  # signal handlers raise into this path
            primary_error = exc

        if quiescence_started:
            try:
                final_quiescence = self._leave_stopped_and_recoverable()
                self._assert_protected_unchanged(protected_before)
            except BaseException as exc:
                if primary_error is None:
                    primary_error = exc
                else:
                    primary_error = RetryError(
                        f"{type(primary_error).__name__}: {primary_error}; "
                        f"safe-state cleanup failed: {type(exc).__name__}: {exc}"
                    )

        if self.archive_path is not None:
            manifest = {
                "schema_version": "mastermind.executive_acceptance_retry_manifest/v1",
                "expected_sha": self.expected_sha,
                "archive_root": os.fspath(self.archive_path),
                "moved_targets": self.moved,
                "installed_release_preserved": True,
                "worker_auth_preserved_without_reading_contents": True,
                "final_quiescence": final_quiescence,
            }
            try:
                self._write_archive_receipt("archive-manifest.json", manifest)
                self._write_archive_receipt(
                    "archive-complete.json" if primary_error is None else "archive-incomplete.json",
                    {
                        "schema_version": "mastermind.executive_acceptance_retry_archive/v1",
                        "status": "COMPLETE" if primary_error is None else "INCOMPLETE",
                        "finished_at": _now(),
                        "expected_sha": self.expected_sha,
                        "error_type": None if primary_error is None else type(primary_error).__name__,
                        "error": None if primary_error is None else str(primary_error),
                    },
                )
            except BaseException as exc:
                if primary_error is None:
                    primary_error = exc

        if primary_error is not None:
            raise primary_error
        if self.archive_path is None:
            raise RetryError("acceptance archive was not created")
        return self.archive_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Stop Executive services, preserve a failed exact-SHA host proof, "
            "and prepare clean mutable roots for a retry."
        )
    )
    parser.add_argument("--expected-sha", required=True)
    return parser


def _host_retry(expected_sha: str) -> AcceptanceRetry:
    control = pwd.getpwnam(CONTROL_USER)
    worker = pwd.getpwnam(WORKER_USER)
    control_group = grp.getgrnam(CONTROL_GROUP)
    worker_group = grp.getgrnam(WORKER_GROUP)
    wheel = grp.getgrnam("wheel")
    release = Path(__file__).resolve().parents[2]
    return AcceptanceRetry(
        expected_sha=expected_sha,
        release=release,
        layout=HostLayout(),
        principals=PrincipalIds(
            control_uid=control.pw_uid,
            control_gid=control_group.gr_gid,
            worker_uid=worker.pw_uid,
            worker_gid=worker_group.gr_gid,
            wheel_gid=wheel.gr_gid,
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    def interrupted(signum: int, _frame: Any) -> None:
        raise RetryInterrupted(f"received signal {signum}")

    prior_handlers = {
        signum: signal.signal(signum, interrupted)
        for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM)
    }
    try:
        retry = _host_retry(args.expected_sha)
        archive = retry.run()
    except (KeyError, OSError, RetryError, subprocess.TimeoutExpired) as exc:
        print(f"acceptance retry error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        for signum, handler in prior_handlers.items():
            signal.signal(signum, handler)
    print(f"acceptance retry ready; prior evidence archive: {archive}")
    print("Executive services are disabled and stopped; rerun acceptance.sh explicitly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
