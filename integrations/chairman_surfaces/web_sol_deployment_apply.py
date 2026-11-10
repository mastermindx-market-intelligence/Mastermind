"""Transactional filesystem application for one reviewed Web-Sol deployment bundle.

The existing :mod:`web_sol_deployment` module remains the pure renderer and
planner.  This module owns only the bounded local filesystem transaction used by
the separate INSTALL1 proof carrier.  It performs no browser, profile, account,
credential, network, provider, Runtime, or lifecycle action.
"""
from __future__ import annotations

import ctypes
import dataclasses
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

from . import web_sol_deployment as deployment

PREPARED_RECEIPT_SCHEMA = "mastermind.web_sol_deployment_prepared_receipt.v1"
MAX_PREIMAGE_BYTES = 1_048_576
MAX_TOTAL_PREIMAGE_BYTES = 4_194_304

_OPERATION_RE = re.compile(r"\A[a-z0-9][a-z0-9-]{0,127}\Z")
_CLEANUP_NONCE_RE = re.compile(r"\A[0-9a-f]{32}\Z")

_PRIVATE_DIRECTORY_MODE = stat.S_IRWXU
_PERMISSION_BITS_MASK = stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO


class WebSolDeploymentApplyError(ValueError):
    """One payload-free transactional-applier refusal."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclasses.dataclass(frozen=True)
class ArtifactPreimage:
    kind: str
    path: Path
    path_digest: str
    prior_state: str
    prior_bytes: bytes | None
    prior_sha256: str | None
    prior_mode: int | None
    prior_uid: int | None
    prior_gid: int | None


@dataclasses.dataclass(frozen=True)
class DirectoryPreimage:
    path: Path
    path_digest: str
    prior_state: str
    prior_dev: int | None
    prior_ino: int | None
    prior_mode: int | None
    prior_uid: int | None
    prior_gid: int | None


@dataclasses.dataclass
class PreparedDeployment:
    operation_key: str
    bundle: deployment.DeploymentBundle
    plan: deployment.DeploymentPlan
    install_root: Path
    expected_uid: int
    expected_gid: int
    preimages: tuple[ArtifactPreimage, ...]
    directory_preimages: tuple[DirectoryPreimage, ...]
    cleanup_nonce: str
    prepared_digest: str
    _state: str = dataclasses.field(default="PREPARED", repr=False)

    @property
    def public_receipt(self) -> dict[str, object]:
        counts = {"CREATE": 0, "UPDATE": 0, "UNCHANGED": 0}
        for row in self.plan.changes:
            if row.action not in counts:
                raise WebSolDeploymentApplyError("PLAN_INVALID")
            counts[row.action] += 1
        return {
            "schema": PREPARED_RECEIPT_SCHEMA,
            "status": "PREPARED",
            "operation_key": self.operation_key,
            "bundle_digest": self.bundle.bundle_digest,
            "prepared_digest": self.prepared_digest,
            "target_count": len(self.preimages),
            "create_count": counts["CREATE"],
            "update_count": counts["UPDATE"],
            "unchanged_count": counts["UNCHANGED"],
            "production_acceptance_granted": False,
        }


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _operation_key(value: Any) -> str:
    if not isinstance(value, str) or _OPERATION_RE.fullmatch(value) is None:
        raise WebSolDeploymentApplyError("OPERATION_INVALID")
    return value


def _cleanup_nonce(value: Any) -> str:
    if type(value) is not str or _CLEANUP_NONCE_RE.fullmatch(value) is None:
        raise WebSolDeploymentApplyError("PREPARED_INTEGRITY_MISMATCH")
    return value


def _install_root(value: str | Path, *, uid: int, gid: int) -> Path:
    root = value if isinstance(value, Path) else Path(value)
    if not root.is_absolute() or ".." in root.parts:
        raise WebSolDeploymentApplyError("INSTALL_ROOT_INVALID")
    try:
        info = root.lstat()
    except OSError as exc:
        raise WebSolDeploymentApplyError("INSTALL_ROOT_INVALID") from exc
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise WebSolDeploymentApplyError("INSTALL_ROOT_INVALID")
    if info.st_uid != uid or info.st_gid != gid or stat.S_IMODE(info.st_mode) & 0o022:
        raise WebSolDeploymentApplyError("INSTALL_ROOT_OWNERSHIP_INVALID")
    return root


def _relative_target(path: Path, root: Path) -> None:
    if not path.is_absolute() or ".." in path.parts:
        raise WebSolDeploymentApplyError("TARGET_OUTSIDE_ROOT")
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise WebSolDeploymentApplyError("TARGET_OUTSIDE_ROOT") from exc
    if not relative.parts:
        raise WebSolDeploymentApplyError("TARGET_OUTSIDE_ROOT")


def _plan_rows(
    bundle: deployment.DeploymentBundle,
    plan: deployment.DeploymentPlan,
) -> dict[str, deployment.DeploymentChange]:
    if not isinstance(bundle, deployment.DeploymentBundle):
        raise WebSolDeploymentApplyError("BUNDLE_INVALID")
    if not isinstance(plan, deployment.DeploymentPlan):
        raise WebSolDeploymentApplyError("PLAN_INVALID")
    if plan.bundle_digest != bundle.bundle_digest:
        raise WebSolDeploymentApplyError("PLAN_MISMATCH")
    rows: dict[str, deployment.DeploymentChange] = {}
    for change in plan.changes:
        key = str(change.path)
        if key in rows:
            raise WebSolDeploymentApplyError("TARGET_DUPLICATE")
        rows[key] = change
    artifact_paths = [str(item.destination) for item in bundle.artifacts]
    if len(artifact_paths) != len(set(artifact_paths)):
        raise WebSolDeploymentApplyError("TARGET_DUPLICATE")
    if set(rows) != set(artifact_paths):
        raise WebSolDeploymentApplyError("PLAN_MISMATCH")
    return rows


def _capture_directory_preimages(
    paths: set[Path],
    *,
    expected_uid: int,
    expected_gid: int,
) -> tuple[DirectoryPreimage, ...]:
    rows: list[DirectoryPreimage] = []
    for path in sorted(paths, key=lambda item: (len(item.parts), str(item))):
        try:
            info = path.lstat()
        except FileNotFoundError:
            rows.append(
                DirectoryPreimage(
                    path=path,
                    path_digest=_sha256(str(path).encode("utf-8")),
                    prior_state="ABSENT",
                    prior_dev=None,
                    prior_ino=None,
                    prior_mode=None,
                    prior_uid=None,
                    prior_gid=None,
                )
            )
            continue
        except OSError as exc:
            raise WebSolDeploymentApplyError("DIRECTORY_READ_FAILED") from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise WebSolDeploymentApplyError("TARGET_SYMLINK_REFUSED")
        mode = stat.S_IMODE(info.st_mode)
        if info.st_uid != expected_uid or info.st_gid != expected_gid:
            raise WebSolDeploymentApplyError("DIRECTORY_OWNER_MISMATCH")
        if mode & 0o022:
            raise WebSolDeploymentApplyError("DIRECTORY_MODE_MISMATCH")
        rows.append(
            DirectoryPreimage(
                path=path,
                path_digest=_sha256(str(path).encode("utf-8")),
                prior_state="PRESENT",
                prior_dev=info.st_dev,
                prior_ino=info.st_ino,
                prior_mode=mode,
                prior_uid=info.st_uid,
                prior_gid=info.st_gid,
            )
        )
    return tuple(rows)


def _read_named_regular_file_at(
    parent_descriptor: int,
    name: str,
    *,
    expected_uid: int,
    expected_gid: int,
) -> tuple[os.stat_result, bytes]:
    """Read one exact regular file through an already-confined parent fd."""

    if not name or name in {".", ".."} or "/" in name or "\x00" in name:
        raise WebSolDeploymentApplyError("TARGET_READ_FAILED")
    try:
        named = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except OSError as exc:
        raise WebSolDeploymentApplyError("TARGET_READ_FAILED") from exc
    if stat.S_ISLNK(named.st_mode) or not stat.S_ISREG(named.st_mode):
        raise WebSolDeploymentApplyError("TARGET_SYMLINK_REFUSED")
    if named.st_size > MAX_PREIMAGE_BYTES:
        raise WebSolDeploymentApplyError("PREIMAGE_TOO_LARGE")
    if named.st_nlink != 1:
        raise WebSolDeploymentApplyError("TARGET_LINK_COUNT_INVALID")
    if named.st_uid != expected_uid or named.st_gid != expected_gid:
        raise WebSolDeploymentApplyError("TARGET_OWNER_MISMATCH")
    if not hasattr(os, "O_NOFOLLOW"):
        raise WebSolDeploymentApplyError("DIRECTORY_DESCRIPTOR_UNAVAILABLE")
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=parent_descriptor,
        )
    except OSError as exc:
        raise WebSolDeploymentApplyError("TARGET_READ_FAILED") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_uid != expected_uid
            or opened.st_gid != expected_gid
        ):
            raise WebSolDeploymentApplyError("PREIMAGE_CONFLICT")
        payload = bytearray()
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            if len(payload) + len(chunk) > MAX_PREIMAGE_BYTES:
                raise WebSolDeploymentApplyError("PREIMAGE_TOO_LARGE")
            payload.extend(chunk)
        final = os.fstat(descriptor)
        if (
            final.st_dev,
            final.st_ino,
            final.st_size,
            final.st_mtime_ns,
        ) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
        ) or len(payload) != final.st_size:
            raise WebSolDeploymentApplyError("PREIMAGE_CONFLICT")
        return final, bytes(payload)
    except OSError as exc:
        raise WebSolDeploymentApplyError("TARGET_READ_FAILED") from exc
    finally:
        os.close(descriptor)


def _prepared_digest_from_state(
    *,
    operation_key: str,
    bundle: deployment.DeploymentBundle,
    plan: deployment.DeploymentPlan,
    expected_uid: int,
    expected_gid: int,
    cleanup_nonce: str,
    preimages: tuple[ArtifactPreimage, ...] | list[ArtifactPreimage],
    directory_preimages: tuple[DirectoryPreimage, ...] | list[DirectoryPreimage],
) -> str:
    try:
        nonce = _cleanup_nonce(cleanup_nonce)
        plan_rows = _plan_rows(bundle, plan)
        artifacts = {str(row.destination): row for row in bundle.artifacts}
        target_rows: list[dict[str, object]] = []
        for row in sorted(preimages, key=lambda item: str(item.path)):
            artifact = artifacts[str(row.path)]
            change = plan_rows[str(row.path)]
            if row.kind != artifact.kind:
                raise WebSolDeploymentApplyError("PREPARED_INTEGRITY_MISMATCH")
            target_rows.append(
                {
                    "kind": row.kind,
                    "path_digest": row.path_digest,
                    "prior_state": row.prior_state,
                    "prior_sha256": row.prior_sha256,
                    "prior_mode": row.prior_mode,
                    "prior_uid": row.prior_uid,
                    "prior_gid": row.prior_gid,
                    "action": change.action,
                    "next_sha256": change.next_sha256,
                    "next_mode": change.mode,
                }
            )
        if len(target_rows) != len(bundle.artifacts):
            raise WebSolDeploymentApplyError("PREPARED_INTEGRITY_MISMATCH")
        directory_rows = [
            {
                "path_digest": row.path_digest,
                "prior_state": row.prior_state,
                "prior_dev": row.prior_dev,
                "prior_ino": row.prior_ino,
                "prior_mode": row.prior_mode,
                "prior_uid": row.prior_uid,
                "prior_gid": row.prior_gid,
            }
            for row in sorted(
                directory_preimages,
                key=lambda item: (len(item.path.parts), str(item.path)),
            )
        ]
    except (KeyError, TypeError, AttributeError) as exc:
        raise WebSolDeploymentApplyError("PREPARED_INTEGRITY_MISMATCH") from exc
    return _sha256(
        _canonical_bytes(
            {
                "schema": "mastermind.web_sol_deployment_prepared.v1",
                "operation_key": operation_key,
                "bundle_digest": bundle.bundle_digest,
                "expected_uid": expected_uid,
                "expected_gid": expected_gid,
                "cleanup_nonce": nonce,
                "directories": directory_rows,
                "targets": target_rows,
            }
        )
    )


def prepare_deployment(
    bundle: deployment.DeploymentBundle,
    plan: deployment.DeploymentPlan,
    *,
    install_root: str | Path,
    expected_uid: int,
    expected_gid: int,
    operation_key: str,
) -> PreparedDeployment:
    """Capture exact file and directory preimages before any mutation."""

    if type(expected_uid) is not int or expected_uid < 0:
        raise WebSolDeploymentApplyError("OWNER_INVALID")
    if type(expected_gid) is not int or expected_gid < 0:
        raise WebSolDeploymentApplyError("OWNER_INVALID")
    operation = _operation_key(operation_key)
    try:
        cleanup_nonce = _cleanup_nonce(os.urandom(16).hex())
    except OSError as exc:
        raise WebSolDeploymentApplyError("CLEANUP_NONCE_UNAVAILABLE") from exc
    root = _install_root(install_root, uid=expected_uid, gid=expected_gid)
    rows = _plan_rows(bundle, plan)
    artifacts = sorted(bundle.artifacts, key=lambda row: str(row.destination))

    directory_paths = {root}
    for artifact in artifacts:
        _relative_target(artifact.destination, root)
        directory_paths.update(_parent_chain(artifact.destination, root))
    directory_preimages = _capture_directory_preimages(
        directory_paths,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )

    provisional = PreparedDeployment(
        operation_key=operation,
        bundle=bundle,
        plan=plan,
        install_root=root,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        preimages=(),
        directory_preimages=directory_preimages,
        cleanup_nonce=cleanup_nonce,
        prepared_digest="",
    )
    directories_by_path = {row.path: row for row in directory_preimages}

    preimages: list[ArtifactPreimage] = []
    total_preimage_bytes = 0
    for artifact in artifacts:
        target = artifact.destination
        change = rows[str(target)]
        if change.next_sha256 != artifact.sha256 or change.mode != artifact.mode:
            raise WebSolDeploymentApplyError("PLAN_MISMATCH")

        chain = _parent_chain(target, root)
        parent_absent = any(
            directories_by_path[path].prior_state == "ABSENT"
            for path in chain
        )
        info: os.stat_result | None = None
        content: bytes | None = None
        if not parent_absent:
            parent_descriptor = _open_verified_directory(target.parent, provisional)
            try:
                try:
                    os.stat(
                        target.name,
                        dir_fd=parent_descriptor,
                        follow_symlinks=False,
                    )
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    raise WebSolDeploymentApplyError("TARGET_READ_FAILED") from exc
                else:
                    info, content = _read_named_regular_file_at(
                        parent_descriptor,
                        target.name,
                        expected_uid=expected_uid,
                        expected_gid=expected_gid,
                    )
                if not _directory_binding_current(
                    parent_descriptor,
                    target.parent,
                    provisional,
                ):
                    raise WebSolDeploymentApplyError("PREIMAGE_CONFLICT")
            finally:
                os.close(parent_descriptor)

        if info is None:
            if change.action != "CREATE" or change.prior_sha256 is not None:
                raise WebSolDeploymentApplyError("PREIMAGE_CONFLICT")
            row = ArtifactPreimage(
                kind=artifact.kind,
                path=target,
                path_digest=_sha256(str(target).encode("utf-8")),
                prior_state="ABSENT",
                prior_bytes=None,
                prior_sha256=None,
                prior_mode=None,
                prior_uid=None,
                prior_gid=None,
            )
        else:
            if content is None:
                raise WebSolDeploymentApplyError("TARGET_READ_FAILED")
            total_preimage_bytes += len(content)
            if total_preimage_bytes > MAX_TOTAL_PREIMAGE_BYTES:
                raise WebSolDeploymentApplyError("PREIMAGE_TOO_LARGE")
            prior_sha = _sha256(content)
            expected_action = "UNCHANGED" if content == artifact.content else "UPDATE"
            if change.action != expected_action or change.prior_sha256 != prior_sha:
                raise WebSolDeploymentApplyError("PREIMAGE_CONFLICT")
            mode = stat.S_IMODE(info.st_mode)
            if change.action == "UNCHANGED" and mode != artifact.mode:
                raise WebSolDeploymentApplyError("TARGET_MODE_MISMATCH")
            row = ArtifactPreimage(
                kind=artifact.kind,
                path=target,
                path_digest=_sha256(str(target).encode("utf-8")),
                prior_state="PRESENT",
                prior_bytes=content,
                prior_sha256=prior_sha,
                prior_mode=mode,
                prior_uid=info.st_uid,
                prior_gid=info.st_gid,
            )
        preimages.append(row)

    prepared_digest = _prepared_digest_from_state(
        operation_key=operation,
        bundle=bundle,
        plan=plan,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        cleanup_nonce=cleanup_nonce,
        preimages=preimages,
        directory_preimages=directory_preimages,
    )
    return PreparedDeployment(
        operation_key=operation,
        bundle=bundle,
        plan=plan,
        install_root=root,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        preimages=tuple(preimages),
        directory_preimages=directory_preimages,
        cleanup_nonce=cleanup_nonce,
        prepared_digest=prepared_digest,
    )


__all__ = [
    "ArtifactPreimage",
    "DirectoryPreimage",
    "MAX_PREIMAGE_BYTES",
    "MAX_TOTAL_PREIMAGE_BYTES",
    "PREPARED_RECEIPT_SCHEMA",
    "PreparedDeployment",
    "WebSolDeploymentApplyError",
    "prepare_deployment",
]

APPLY_RECEIPT_SCHEMA = "mastermind.web_sol_deployment_apply_receipt.v1"
READBACK_RECEIPT_SCHEMA = "mastermind.web_sol_deployment_apply_readback.v1"
ROLLBACK_RECEIPT_SCHEMA = "mastermind.web_sol_deployment_apply_rollback.v1"


@dataclasses.dataclass
class AppliedDeployment:
    prepared: PreparedDeployment
    changed_paths: tuple[Path, ...]
    created_directories: tuple[Path, ...]
    reconciled_paths: tuple[Path, ...]
    _state: str = dataclasses.field(default="APPLIED", repr=False)

    @property
    def public_receipt(self) -> dict[str, object]:
        unchanged = len(self.prepared.preimages) - len(self.changed_paths)
        return {
            "schema": APPLY_RECEIPT_SCHEMA,
            "status": "APPLIED_VERIFIED",
            "operation_key": self.prepared.operation_key,
            "bundle_digest": self.prepared.bundle.bundle_digest,
            "prepared_digest": self.prepared.prepared_digest,
            "target_count": len(self.prepared.preimages),
            "changed_count": len(self.changed_paths),
            "unchanged_count": unchanged,
            "reconciled_count": len(self.reconciled_paths),
            "production_acceptance_granted": False,
        }


def _directory_preimage_for_path(
    path: Path,
    prepared: PreparedDeployment,
) -> DirectoryPreimage:
    matches = [row for row in prepared.directory_preimages if row.path == path]
    if len(matches) != 1:
        raise WebSolDeploymentApplyError("PREPARED_INTEGRITY_MISMATCH")
    return matches[0]


def _opened_directory_matches(
    descriptor: int,
    path: Path,
    prepared: PreparedDeployment,
) -> bool:
    try:
        info = os.fstat(descriptor)
    except OSError:
        return False
    row = _directory_preimage_for_path(path, prepared)
    mode = stat.S_IMODE(info.st_mode)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != prepared.expected_uid
        or info.st_gid != prepared.expected_gid
        or mode & 0o022
    ):
        return False
    if row.prior_state == "PRESENT":
        return (
            info.st_dev == row.prior_dev
            and info.st_ino == row.prior_ino
            and mode == row.prior_mode
            and info.st_uid == row.prior_uid
            and info.st_gid == row.prior_gid
        )
    return row.prior_state == "ABSENT" and mode == _PRIVATE_DIRECTORY_MODE


def _directory_binding_current(
    descriptor: int,
    path: Path,
    prepared: PreparedDeployment,
) -> bool:
    try:
        named = path.lstat()
        opened = os.fstat(descriptor)
    except OSError:
        return False
    return (
        stat.S_ISDIR(named.st_mode)
        and not stat.S_ISLNK(named.st_mode)
        and (named.st_dev, named.st_ino) == (opened.st_dev, opened.st_ino)
        and _opened_directory_matches(descriptor, path, prepared)
    )


def _open_verified_directory(
    path: Path,
    prepared: PreparedDeployment,
) -> int:
    try:
        relative = path.relative_to(prepared.install_root)
    except ValueError as exc:
        raise WebSolDeploymentApplyError("TARGET_OUTSIDE_ROOT") from exc
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise WebSolDeploymentApplyError("DIRECTORY_DESCRIPTOR_UNAVAILABLE")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        descriptor = os.open(prepared.install_root, flags)
    except OSError as exc:
        raise WebSolDeploymentApplyError("DIRECTORY_PREIMAGE_CONFLICT") from exc
    current = prepared.install_root
    try:
        if not _directory_binding_current(descriptor, current, prepared):
            raise WebSolDeploymentApplyError("DIRECTORY_PREIMAGE_CONFLICT")
        for part in relative.parts:
            if not part or part in {".", ".."} or "/" in part or "\x00" in part:
                raise WebSolDeploymentApplyError("TARGET_OUTSIDE_ROOT")
            try:
                next_descriptor = os.open(part, flags, dir_fd=descriptor)
            except OSError as exc:
                raise WebSolDeploymentApplyError("DIRECTORY_PREIMAGE_CONFLICT") from exc
            current = current / part
            if not _directory_binding_current(next_descriptor, current, prepared):
                os.close(next_descriptor)
                raise WebSolDeploymentApplyError("DIRECTORY_PREIMAGE_CONFLICT")
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _parent_chain(target: Path, root: Path) -> tuple[Path, ...]:
    relative = target.parent.relative_to(root)
    current = root
    rows: list[Path] = []
    for part in relative.parts:
        current = current / part
        rows.append(current)
    return tuple(rows)


def _deepest_present_directory_ancestor(
    path: Path,
    prepared: PreparedDeployment,
) -> DirectoryPreimage:
    candidates = [
        row
        for row in prepared.directory_preimages
        if row.prior_state == "PRESENT"
        and (row.path == path or row.path in path.parents)
    ]
    if not candidates:
        raise WebSolDeploymentApplyError("PREPARED_INTEGRITY_MISMATCH")
    return max(candidates, key=lambda row: len(row.path.parts))


def _current_matches_directory_preimage(
    row: DirectoryPreimage,
    prepared: PreparedDeployment,
) -> bool:
    try:
        if row.prior_state == "PRESENT":
            descriptor = _open_verified_directory(row.path, prepared)
            try:
                return _directory_binding_current(
                    descriptor,
                    row.path,
                    prepared,
                )
            finally:
                os.close(descriptor)
        if row.prior_state != "ABSENT":
            return False
        ancestor = _deepest_present_directory_ancestor(row.path, prepared)
        relative = row.path.relative_to(ancestor.path)
        if not relative.parts:
            return False
        descriptor = _open_verified_directory(ancestor.path, prepared)
        try:
            return (
                _named_entry_absent(descriptor, relative.parts[0])
                and _directory_binding_current(
                    descriptor,
                    ancestor.path,
                    prepared,
                )
            )
        finally:
            os.close(descriptor)
    except (OSError, WebSolDeploymentApplyError, ValueError):
        return False


def _current_matches_preimage(
    row: ArtifactPreimage,
    prepared: PreparedDeployment,
) -> bool:
    absent_parents = [
        directory
        for directory in prepared.directory_preimages
        if directory.prior_state == "ABSENT"
        and (
            directory.path == row.path.parent
            or directory.path in row.path.parent.parents
        )
    ]
    try:
        descriptor = _open_verified_directory(row.path.parent, prepared)
    except (OSError, WebSolDeploymentApplyError):
        if row.prior_state != "ABSENT" or not absent_parents:
            return False
        shallowest = min(absent_parents, key=lambda item: len(item.path.parts))
        return _current_matches_directory_preimage(shallowest, prepared)
    try:
        if row.prior_state == "ABSENT":
            matches = _named_entry_absent(descriptor, row.path.name)
        elif row.prior_state == "PRESENT":
            matches = _named_preimage_matches(
                descriptor,
                row.path.name,
                row,
                prepared,
            )
        else:
            return False
        return matches and _directory_binding_current(
            descriptor,
            row.path.parent,
            prepared,
        )
    finally:
        os.close(descriptor)


def _current_matches_artifact(
    artifact: deployment.DeploymentArtifact,
    prepared: PreparedDeployment,
) -> bool:
    try:
        descriptor = _open_verified_directory(
            artifact.destination.parent,
            prepared,
        )
    except (OSError, WebSolDeploymentApplyError):
        return False
    try:
        return (
            _named_file_matches(
                descriptor,
                artifact.destination.name,
                artifact.content,
                artifact.mode,
                prepared,
            )
            and _directory_binding_current(
                descriptor,
                artifact.destination.parent,
                prepared,
            )
        )
    finally:
        os.close(descriptor)


def _validate_prepared_digest(prepared: PreparedDeployment) -> None:
    if not isinstance(prepared, PreparedDeployment):
        raise WebSolDeploymentApplyError("PREPARED_INVALID")
    try:
        current_digest = _prepared_digest_from_state(
            operation_key=prepared.operation_key,
            bundle=prepared.bundle,
            plan=prepared.plan,
            expected_uid=prepared.expected_uid,
            expected_gid=prepared.expected_gid,
            cleanup_nonce=prepared.cleanup_nonce,
            preimages=prepared.preimages,
            directory_preimages=prepared.directory_preimages,
        )
    except WebSolDeploymentApplyError as exc:
        raise WebSolDeploymentApplyError("PREPARED_INTEGRITY_MISMATCH") from exc
    if current_digest != prepared.prepared_digest:
        raise WebSolDeploymentApplyError("PREPARED_INTEGRITY_MISMATCH")


def _assert_prepared_integrity(prepared: PreparedDeployment) -> None:
    _validate_prepared_digest(prepared)
    if prepared._state != "PREPARED":
        raise WebSolDeploymentApplyError("TRANSACTION_CONSUMED")


def _assert_prepared(prepared: PreparedDeployment) -> None:
    _assert_prepared_integrity(prepared)
    if any(
        not _current_matches_directory_preimage(row, prepared)
        for row in prepared.directory_preimages
    ):
        raise WebSolDeploymentApplyError("PREIMAGE_CONFLICT")
    if any(
        not _current_matches_preimage(row, prepared)
        for row in prepared.preimages
    ):
        raise WebSolDeploymentApplyError("PREIMAGE_CONFLICT")


def _created_directory_matches(
    parent_descriptor: int,
    name: str,
    prepared: PreparedDeployment,
) -> bool:
    if not name or name in {".", ".."} or "/" in name or "\x00" in name:
        return False
    try:
        info = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except OSError:
        return False
    return (
        stat.S_ISDIR(info.st_mode)
        and not stat.S_ISLNK(info.st_mode)
        and info.st_uid == prepared.expected_uid
        and info.st_gid == prepared.expected_gid
        and stat.S_IMODE(info.st_mode) == _PRIVATE_DIRECTORY_MODE
    )


def _create_parent_directories(
    prepared: PreparedDeployment,
    created: list[Path],
) -> None:
    absent = [
        row for row in prepared.directory_preimages
        if row.prior_state == "ABSENT"
    ]
    for row in sorted(absent, key=lambda item: (len(item.path.parts), str(item.path))):
        directory = row.path
        parent_descriptor = _open_verified_directory(directory.parent, prepared)
        try:
            try:
                os.stat(
                    directory.name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise WebSolDeploymentApplyError(
                    "DIRECTORY_PREIMAGE_CONFLICT"
                ) from exc
            else:
                raise WebSolDeploymentApplyError("DIRECTORY_PREIMAGE_CONFLICT")
            try:
                os.mkdir(directory.name, _PRIVATE_DIRECTORY_MODE, dir_fd=parent_descriptor)
                os.fsync(parent_descriptor)
            except OSError as exc:
                raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN") from exc
            if not _created_directory_matches(
                parent_descriptor, directory.name, prepared
            ):
                raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN")
            child_descriptor = os.open(
                directory.name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent_descriptor,
            )
            try:
                if not _directory_binding_current(
                    child_descriptor, directory, prepared
                ):
                    raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN")
            finally:
                os.close(child_descriptor)
            created.append(directory)
        finally:
            os.close(parent_descriptor)



def _named_file_matches(
    parent_descriptor: int,
    name: str,
    content: bytes,
    mode: int,
    prepared: PreparedDeployment,
) -> bool:
    if not name or name in {".", ".."} or "/" in name or "\x00" in name:
        return False
    try:
        named = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except OSError:
        return False
    if (
        stat.S_ISLNK(named.st_mode)
        or not stat.S_ISREG(named.st_mode)
        or named.st_nlink != 1
        or named.st_uid != prepared.expected_uid
        or named.st_gid != prepared.expected_gid
        or stat.S_IMODE(named.st_mode) != mode
    ):
        return False
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(name, flags, dir_fd=parent_descriptor)
    except OSError:
        return False
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino):
            return False
        payload = bytearray()
        while len(payload) <= len(content):
            chunk = os.read(descriptor, min(65536, len(content) + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        final = os.fstat(descriptor)
        if (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
        ):
            return False
        return bytes(payload) == content
    except OSError:
        return False
    finally:
        os.close(descriptor)


def _remove_owned_partial_temporary_at(
    parent_descriptor: int,
    name: str,
    *,
    created_dev: int,
    created_ino: int,
    prepared: PreparedDeployment,
) -> None:
    try:
        info = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        identity = (
            info.st_dev,
            info.st_ino,
            info.st_mode,
            info.st_nlink,
            info.st_uid,
            info.st_gid,
        )
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_dev != created_dev
            or info.st_ino != created_ino
            or info.st_uid != prepared.expected_uid
            or info.st_gid != prepared.expected_gid
        ):
            raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN")
        if not _named_entry_identity_matches(
            parent_descriptor,
            name,
            identity,
        ):
            raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN")
        os.unlink(name, dir_fd=parent_descriptor)
        os.fsync(parent_descriptor)
        if not _named_entry_absent(parent_descriptor, name):
            raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN")
    except WebSolDeploymentApplyError:
        raise
    except OSError as exc:
        raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN") from exc


def _write_exact_temporary_at(
    parent_descriptor: int,
    name: str,
    content: bytes,
    mode: int,
    prepared: PreparedDeployment,
) -> None:
    if type(content) is not bytes or type(mode) is not int or not 0 <= mode <= _PERMISSION_BITS_MASK:
        raise WebSolDeploymentApplyError("TEMPORARY_INPUT_INVALID")
    try:
        os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise WebSolDeploymentApplyError("TEMPORARY_PATH_CONFLICT") from exc
    else:
        raise WebSolDeploymentApplyError("TEMPORARY_PATH_CONFLICT")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(name, flags, 0o600, dir_fd=parent_descriptor)
    created = os.fstat(descriptor)
    failure: OSError | None = None
    try:
        view = memoryview(content)
        offset = 0
        while offset < len(view):
            written = os.write(descriptor, view[offset:])
            if written <= 0:
                raise OSError("zero progress")
            offset += written
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
    except OSError as exc:
        failure = exc
    finally:
        try:
            os.close(descriptor)
        except OSError as close_exc:
            if failure is None:
                failure = close_exc
    if failure is not None:
        _remove_owned_partial_temporary_at(
            parent_descriptor,
            name,
            created_dev=created.st_dev,
            created_ino=created.st_ino,
            prepared=prepared,
        )
        raise WebSolDeploymentApplyError("TEMPORARY_WRITE_FAILED") from failure
    if not _named_file_matches(parent_descriptor, name, content, mode, prepared):
        raise WebSolDeploymentApplyError("TEMPORARY_READBACK_MISMATCH")


def _cleanup_quarantine_name(
    name: str,
    prepared: PreparedDeployment,
) -> str:
    if not name or name in {".", ".."} or "/" in name or "\x00" in name:
        raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN")
    nonce = _cleanup_nonce(prepared.cleanup_nonce)
    digest = hashlib.sha256(
        f"{nonce}\0{name}".encode("utf-8")
    ).hexdigest()[:24]
    return f".mmx-clean-{digest}.tmp"


def _restore_quarantined_entry_at(
    parent_descriptor: int,
    quarantine_name: str,
    original_name: str,
    *,
    effect_unknown_code: str,
) -> None:
    try:
        identity = _named_entry_identity(parent_descriptor, quarantine_name)
    except OSError as exc:
        raise WebSolDeploymentApplyError(effect_unknown_code) from exc
    try:
        _atomic_rename_at(
            parent_descriptor,
            quarantine_name,
            original_name,
            exchange=False,
        )
    except OSError as exc:
        if not (
            _named_entry_identity_matches(
                parent_descriptor,
                original_name,
                identity,
            )
            and _named_entry_absent(parent_descriptor, quarantine_name)
        ):
            raise WebSolDeploymentApplyError(effect_unknown_code) from exc
    if not (
        _named_entry_identity_matches(parent_descriptor, original_name, identity)
        and _named_entry_absent(parent_descriptor, quarantine_name)
    ):
        raise WebSolDeploymentApplyError(effect_unknown_code)
    try:
        os.fsync(parent_descriptor)
    except OSError as exc:
        raise WebSolDeploymentApplyError(effect_unknown_code) from exc


def _cleanup_exact_temporary_at(
    parent_descriptor: int,
    name: str,
    content: bytes,
    mode: int,
    prepared: PreparedDeployment,
    *,
    effect_unknown_code: str = "APPLY_EFFECT_UNKNOWN",
) -> bool:
    """Quarantine one owned temporary and refuse detected pathname substitution.

    The final removal is necessarily pathname-based on supported Darwin/Linux
    APIs, so an identity check is performed immediately before unlink and the
    private quarantine name is transaction-randomized to narrow the residual
    same-uid race.
    """

    if effect_unknown_code not in {
        "APPLY_EFFECT_UNKNOWN",
        "ROLLBACK_EFFECT_UNKNOWN",
    }:
        raise WebSolDeploymentApplyError("PREPARED_INTEGRITY_MISMATCH")
    quarantine_name = _cleanup_quarantine_name(name, prepared)
    source_absent = _named_entry_absent(parent_descriptor, name)
    quarantine_absent = _named_entry_absent(parent_descriptor, quarantine_name)
    if source_absent and quarantine_absent:
        return False
    if not source_absent and not quarantine_absent:
        raise WebSolDeploymentApplyError(effect_unknown_code)

    if not source_absent:
        try:
            _atomic_rename_at(
                parent_descriptor,
                name,
                quarantine_name,
                exchange=False,
            )
        except OSError as exc:
            if not (
                _named_entry_absent(parent_descriptor, name)
                and _named_file_matches(
                    parent_descriptor,
                    quarantine_name,
                    content,
                    mode,
                    prepared,
                )
            ):
                raise WebSolDeploymentApplyError(effect_unknown_code) from exc

    if not _named_entry_absent(parent_descriptor, name):
        raise WebSolDeploymentApplyError(effect_unknown_code)
    try:
        quarantine_identity = _named_entry_identity(
            parent_descriptor, quarantine_name
        )
    except OSError as exc:
        raise WebSolDeploymentApplyError(effect_unknown_code) from exc
    if not _named_file_matches(
        parent_descriptor,
        quarantine_name,
        content,
        mode,
        prepared,
    ):
        _restore_quarantined_entry_at(
            parent_descriptor,
            quarantine_name,
            name,
            effect_unknown_code=effect_unknown_code,
        )
        raise WebSolDeploymentApplyError(effect_unknown_code)
    if not _named_entry_identity_matches(
        parent_descriptor,
        quarantine_name,
        quarantine_identity,
    ):
        if (
            _named_entry_absent(parent_descriptor, name)
            and not _named_entry_absent(parent_descriptor, quarantine_name)
        ):
            _restore_quarantined_entry_at(
                parent_descriptor,
                quarantine_name,
                name,
                effect_unknown_code=effect_unknown_code,
            )
        raise WebSolDeploymentApplyError(effect_unknown_code)

    try:
        os.unlink(quarantine_name, dir_fd=parent_descriptor)
        os.fsync(parent_descriptor)
    except OSError as exc:
        if not (
            _named_entry_absent(parent_descriptor, name)
            and _named_entry_absent(parent_descriptor, quarantine_name)
        ):
            raise WebSolDeploymentApplyError(effect_unknown_code) from exc
    if not (
        _named_entry_absent(parent_descriptor, name)
        and _named_entry_absent(parent_descriptor, quarantine_name)
    ):
        raise WebSolDeploymentApplyError(effect_unknown_code)
    return True


def _atomic_rename_binding(
    *,
    exchange: bool,
) -> tuple[Any, int]:
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        if sys.platform == "darwin":
            rename = libc.renameatx_np
            flags = (0x00000002 if exchange else 0x00000004) | 0x00000010
        elif sys.platform.startswith("linux"):
            rename = libc.renameat2
            flags = 0x00000002 if exchange else 0x00000001
        else:
            raise AttributeError("atomic rename unavailable")
    except (AttributeError, OSError) as exc:
        raise WebSolDeploymentApplyError("ATOMIC_RENAME_UNAVAILABLE") from exc
    rename.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    rename.restype = ctypes.c_int
    return rename, flags


def _require_atomic_rename_support() -> None:
    _atomic_rename_binding(exchange=False)
    _atomic_rename_binding(exchange=True)


def _atomic_rename_at(
    parent_descriptor: int,
    source_name: str,
    target_name: str,
    *,
    exchange: bool,
) -> None:
    """Atomically exchange two names or rename without replacing a target."""

    for name in (source_name, target_name):
        if not name or name in {".", ".."} or "/" in name or "\x00" in name:
            raise WebSolDeploymentApplyError("ATOMIC_RENAME_INVALID")
    rename, flags = _atomic_rename_binding(exchange=exchange)
    ctypes.set_errno(0)
    if rename(
        parent_descriptor,
        os.fsencode(source_name),
        parent_descriptor,
        os.fsencode(target_name),
        flags,
    ) != 0:
        observed_errno = ctypes.get_errno()
        raise OSError(observed_errno, os.strerror(observed_errno))


def _named_entry_identity(
    parent_descriptor: int,
    name: str,
) -> tuple[int, int, int, int, int, int]:
    info = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_uid,
        info.st_gid,
    )


def _named_entry_identity_matches(
    parent_descriptor: int,
    name: str,
    identity: tuple[int, int, int, int, int, int],
) -> bool:
    try:
        return _named_entry_identity(parent_descriptor, name) == identity
    except OSError:
        return False


def _install_absent_target_at(
    parent_descriptor: int,
    temporary_name: str,
    target_name: str,
    artifact: deployment.DeploymentArtifact,
    prepared: PreparedDeployment,
) -> bool:
    """Install one artifact only while its captured target remains absent."""

    reconciled = False
    try:
        _atomic_rename_at(
            parent_descriptor,
            temporary_name,
            target_name,
            exchange=False,
        )
    except OSError as exc:
        if _named_file_matches(
            parent_descriptor,
            target_name,
            artifact.content,
            artifact.mode,
            prepared,
        ) and _named_entry_absent(parent_descriptor, temporary_name):
            reconciled = True
        elif _named_file_matches(
            parent_descriptor,
            temporary_name,
            artifact.content,
            artifact.mode,
            prepared,
        ) and _named_entry_absent(parent_descriptor, target_name):
            _cleanup_exact_temporary_at(
                parent_descriptor,
                temporary_name,
                artifact.content,
                artifact.mode,
                prepared,
            )
            raise
        elif _named_file_matches(
            parent_descriptor,
            temporary_name,
            artifact.content,
            artifact.mode,
            prepared,
        ) and not _named_entry_absent(parent_descriptor, target_name):
            _cleanup_exact_temporary_at(
                parent_descriptor,
                temporary_name,
                artifact.content,
                artifact.mode,
                prepared,
            )
            raise WebSolDeploymentApplyError("PREIMAGE_CONFLICT") from exc
        else:
            raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN") from exc
    try:
        os.fsync(parent_descriptor)
    except OSError as exc:
        if not (
            _named_file_matches(
                parent_descriptor,
                target_name,
                artifact.content,
                artifact.mode,
                prepared,
            )
            and _named_entry_absent(parent_descriptor, temporary_name)
        ):
            raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN") from exc
        try:
            os.fsync(parent_descriptor)
        except OSError as fsync_exc:
            raise WebSolDeploymentApplyError(
                "APPLY_EFFECT_UNKNOWN"
            ) from fsync_exc
        reconciled = True
    if not (
        _named_file_matches(
            parent_descriptor,
            target_name,
            artifact.content,
            artifact.mode,
            prepared,
        )
        and _named_entry_absent(parent_descriptor, temporary_name)
    ):
        raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN")
    return reconciled


def _exchange_exact_target_at(
    parent_descriptor: int,
    temporary_name: str,
    target_name: str,
    *,
    temporary_content: bytes,
    temporary_mode: int,
    expected_target_content: bytes,
    expected_target_mode: int,
    conflict_code: str,
    effect_unknown_code: str,
    prepared: PreparedDeployment,
) -> bool:
    """Exchange one staged file with one exact target and preserve conflicts."""

    reconciled = False
    try:
        _atomic_rename_at(
            parent_descriptor,
            temporary_name,
            target_name,
            exchange=True,
        )
    except OSError as exc:
        if _named_file_matches(
            parent_descriptor,
            target_name,
            temporary_content,
            temporary_mode,
            prepared,
        ) and _named_file_matches(
            parent_descriptor,
            temporary_name,
            expected_target_content,
            expected_target_mode,
            prepared,
        ):
            reconciled = True
        elif _named_file_matches(
            parent_descriptor,
            target_name,
            expected_target_content,
            expected_target_mode,
            prepared,
        ) and _named_file_matches(
            parent_descriptor,
            temporary_name,
            temporary_content,
            temporary_mode,
            prepared,
        ):
            _cleanup_exact_temporary_at(
                parent_descriptor,
                temporary_name,
                temporary_content,
                temporary_mode,
                prepared,
                effect_unknown_code=effect_unknown_code,
            )
            raise
        elif _named_file_matches(
            parent_descriptor,
            temporary_name,
            temporary_content,
            temporary_mode,
            prepared,
        ):
            _cleanup_exact_temporary_at(
                parent_descriptor,
                temporary_name,
                temporary_content,
                temporary_mode,
                prepared,
                effect_unknown_code=effect_unknown_code,
            )
            raise WebSolDeploymentApplyError(conflict_code) from exc
        else:
            raise WebSolDeploymentApplyError(effect_unknown_code) from exc

    if not _named_file_matches(
        parent_descriptor,
        target_name,
        temporary_content,
        temporary_mode,
        prepared,
    ):
        raise WebSolDeploymentApplyError(effect_unknown_code)
    if _named_file_matches(
        parent_descriptor,
        temporary_name,
        expected_target_content,
        expected_target_mode,
        prepared,
    ):
        removed = _cleanup_exact_temporary_at(
            parent_descriptor,
            temporary_name,
            expected_target_content,
            expected_target_mode,
            prepared,
            effect_unknown_code=effect_unknown_code,
        )
        if not removed:
            raise WebSolDeploymentApplyError(effect_unknown_code)
        return reconciled

    try:
        conflicting_identity = _named_entry_identity(
            parent_descriptor,
            temporary_name,
        )
    except OSError as exc:
        raise WebSolDeploymentApplyError(effect_unknown_code) from exc
    try:
        _atomic_rename_at(
            parent_descriptor,
            temporary_name,
            target_name,
            exchange=True,
        )
    except OSError as exc:
        if not (
            _named_entry_identity_matches(
                parent_descriptor,
                target_name,
                conflicting_identity,
            )
            and _named_file_matches(
                parent_descriptor,
                temporary_name,
                temporary_content,
                temporary_mode,
                prepared,
            )
        ):
            raise WebSolDeploymentApplyError(effect_unknown_code) from exc
    if not (
        _named_entry_identity_matches(
            parent_descriptor,
            target_name,
            conflicting_identity,
        )
        and _named_file_matches(
            parent_descriptor,
            temporary_name,
            temporary_content,
            temporary_mode,
            prepared,
        )
    ):
        raise WebSolDeploymentApplyError(effect_unknown_code)
    removed = _cleanup_exact_temporary_at(
        parent_descriptor,
        temporary_name,
        temporary_content,
        temporary_mode,
        prepared,
        effect_unknown_code=effect_unknown_code,
    )
    if not removed:
        raise WebSolDeploymentApplyError(effect_unknown_code)
    raise WebSolDeploymentApplyError(conflict_code)


def _install_present_target_at(
    parent_descriptor: int,
    temporary_name: str,
    target_name: str,
    row: ArtifactPreimage,
    artifact: deployment.DeploymentArtifact,
    prepared: PreparedDeployment,
) -> bool:
    if row.prior_bytes is None or row.prior_mode is None:
        raise WebSolDeploymentApplyError("PREPARED_INTEGRITY_MISMATCH")
    return _exchange_exact_target_at(
        parent_descriptor,
        temporary_name,
        target_name,
        temporary_content=artifact.content,
        temporary_mode=artifact.mode,
        expected_target_content=row.prior_bytes,
        expected_target_mode=row.prior_mode,
        conflict_code="PREIMAGE_CONFLICT",
        effect_unknown_code="APPLY_EFFECT_UNKNOWN",
        prepared=prepared,
    )


def _temporary_path(artifact: deployment.DeploymentArtifact, prepared: PreparedDeployment) -> Path:
    return artifact.destination.with_name(
        f".{artifact.destination.name}.mmx-{prepared.prepared_digest[:16]}.tmp"
    )


def apply_deployment(prepared: PreparedDeployment) -> AppliedDeployment:
    """Apply one prepared bundle exactly once and verify every postimage."""

    _assert_prepared(prepared)
    _require_atomic_rename_support()
    created_directories: list[Path] = []
    artifacts = {
        str(item.destination): item for item in prepared.bundle.artifacts
    }
    changes = {str(item.path): item for item in prepared.plan.changes}
    changed: list[Path] = []
    reconciled: list[Path] = []
    preserved_conflicts: set[Path] = set()

    try:
        _create_parent_directories(prepared, created_directories)
        for row in prepared.preimages:
            artifact = artifacts[str(row.path)]
            change = changes[str(row.path)]
            if change.action == "UNCHANGED":
                if not _current_matches_artifact(artifact, prepared):
                    preserved_conflicts.add(row.path)
                    raise WebSolDeploymentApplyError("PREIMAGE_CONFLICT")
                continue
            temporary = _temporary_path(artifact, prepared)
            parent_descriptor = _open_verified_directory(
                artifact.destination.parent,
                prepared,
            )
            try:
                temporary_name = temporary.name
                target_name = artifact.destination.name
                _write_exact_temporary_at(
                    parent_descriptor,
                    temporary_name,
                    artifact.content,
                    artifact.mode,
                    prepared,
                )
                if not _named_preimage_matches(
                    parent_descriptor,
                    target_name,
                    row,
                    prepared,
                ):
                    preserved_conflicts.add(row.path)
                    raise WebSolDeploymentApplyError("PREIMAGE_CONFLICT")
                try:
                    if row.prior_state == "ABSENT":
                        was_reconciled = _install_absent_target_at(
                            parent_descriptor,
                            temporary_name,
                            target_name,
                            artifact,
                            prepared,
                        )
                    elif row.prior_state == "PRESENT":
                        was_reconciled = _install_present_target_at(
                            parent_descriptor,
                            temporary_name,
                            target_name,
                            row,
                            artifact,
                            prepared,
                        )
                    else:
                        raise WebSolDeploymentApplyError(
                            "PREPARED_INTEGRITY_MISMATCH"
                        )
                except WebSolDeploymentApplyError as exc:
                    if exc.code == "PREIMAGE_CONFLICT":
                        preserved_conflicts.add(row.path)
                    raise
                if was_reconciled:
                    reconciled.append(artifact.destination)
            finally:
                os.close(parent_descriptor)
            if not _current_matches_artifact(artifact, prepared):
                raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN")
            changed.append(artifact.destination)
    except (WebSolDeploymentApplyError, OSError) as exc:
        try:
            _abort_partial_apply(
                prepared,
                created_directories,
                preserved_conflicts=preserved_conflicts,
            )
        except (WebSolDeploymentApplyError, OSError) as abort_exc:
            prepared._state = "EFFECT_UNKNOWN"
            raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN") from abort_exc
        if preserved_conflicts:
            raise WebSolDeploymentApplyError("PREIMAGE_CONFLICT") from exc
        raise WebSolDeploymentApplyError("APPLY_ABORTED_ROLLED_BACK") from exc

    applied = AppliedDeployment(
        prepared=prepared,
        changed_paths=tuple(changed),
        created_directories=tuple(created_directories),
        reconciled_paths=tuple(reconciled),
    )
    prepared._state = "APPLIED"
    verify_applied_deployment(applied)
    return applied


def verify_applied_deployment(applied: AppliedDeployment) -> dict[str, object]:
    """Verify every exact bundle postimage without mutation."""

    if not isinstance(applied, AppliedDeployment) or applied._state != "APPLIED":
        raise WebSolDeploymentApplyError("APPLIED_INVALID")
    if not _postimage_complete(applied.prepared):
        raise WebSolDeploymentApplyError("READBACK_MISMATCH")
    return {
        "schema": READBACK_RECEIPT_SCHEMA,
        "status": "READBACK_VERIFIED",
        "operation_key": applied.prepared.operation_key,
        "bundle_digest": applied.prepared.bundle.bundle_digest,
        "prepared_digest": applied.prepared.prepared_digest,
        "target_count": len(applied.prepared.preimages),
        "production_acceptance_granted": False,
    }


def _named_entry_absent(parent_descriptor: int, name: str) -> bool:
    if not name or name in {".", ".."} or "/" in name or "\x00" in name:
        return False
    try:
        os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return False


def _named_preimage_matches(
    parent_descriptor: int,
    name: str,
    row: ArtifactPreimage,
    prepared: PreparedDeployment,
) -> bool:
    if row.prior_state == "ABSENT":
        return _named_entry_absent(parent_descriptor, name)
    if (
        row.prior_state != "PRESENT"
        or row.prior_bytes is None
        or row.prior_mode is None
    ):
        return False
    return _named_file_matches(
        parent_descriptor,
        name,
        row.prior_bytes,
        row.prior_mode,
        prepared,
    )


def _rollback_absent_target_at(
    parent_descriptor: int,
    quarantine_name: str,
    target_name: str,
    artifact: deployment.DeploymentArtifact,
    prepared: PreparedDeployment,
) -> None:
    """Remove one exact postimage without deleting a concurrent replacement."""

    try:
        _atomic_rename_at(
            parent_descriptor,
            target_name,
            quarantine_name,
            exchange=False,
        )
    except OSError as exc:
        if _named_entry_absent(
            parent_descriptor,
            target_name,
        ) and _named_file_matches(
            parent_descriptor,
            quarantine_name,
            artifact.content,
            artifact.mode,
            prepared,
        ):
            pass
        else:
            raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN") from exc

    if not _named_entry_absent(parent_descriptor, target_name):
        raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN")
    if _named_file_matches(
        parent_descriptor,
        quarantine_name,
        artifact.content,
        artifact.mode,
        prepared,
    ):
        removed = _cleanup_exact_temporary_at(
            parent_descriptor,
            quarantine_name,
            artifact.content,
            artifact.mode,
            prepared,
            effect_unknown_code="ROLLBACK_EFFECT_UNKNOWN",
        )
        if not removed:
            raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN")
        return

    try:
        conflicting_identity = _named_entry_identity(
            parent_descriptor,
            quarantine_name,
        )
    except OSError as exc:
        raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN") from exc
    try:
        _atomic_rename_at(
            parent_descriptor,
            quarantine_name,
            target_name,
            exchange=False,
        )
    except OSError as exc:
        if not (
            _named_entry_identity_matches(
                parent_descriptor,
                target_name,
                conflicting_identity,
            )
            and _named_entry_absent(parent_descriptor, quarantine_name)
        ):
            raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN") from exc
    if not (
        _named_entry_identity_matches(
            parent_descriptor,
            target_name,
            conflicting_identity,
        )
        and _named_entry_absent(parent_descriptor, quarantine_name)
    ):
        raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN")
    try:
        os.fsync(parent_descriptor)
    except OSError as exc:
        raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN") from exc
    raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN")


def _rollback_present_target_at(
    parent_descriptor: int,
    temporary_name: str,
    target_name: str,
    row: ArtifactPreimage,
    artifact: deployment.DeploymentArtifact,
    prepared: PreparedDeployment,
) -> None:
    if row.prior_bytes is None or row.prior_mode is None:
        raise WebSolDeploymentApplyError("ROLLBACK_STATE_INVALID")
    _exchange_exact_target_at(
        parent_descriptor,
        temporary_name,
        target_name,
        temporary_content=row.prior_bytes,
        temporary_mode=row.prior_mode,
        expected_target_content=artifact.content,
        expected_target_mode=artifact.mode,
        conflict_code="ROLLBACK_EFFECT_UNKNOWN",
        effect_unknown_code="ROLLBACK_EFFECT_UNKNOWN",
        prepared=prepared,
    )


def _restore_file(
    row: ArtifactPreimage,
    artifact: deployment.DeploymentArtifact,
    prepared: PreparedDeployment,
) -> None:
    target = row.path
    parent_descriptor = _open_verified_directory(target.parent, prepared)
    try:
        target_name = target.name
        if not _named_file_matches(
            parent_descriptor,
            target_name,
            artifact.content,
            artifact.mode,
            prepared,
        ):
            raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN")

        temporary_name = (
            f".{target.name}.mmx-{prepared.prepared_digest[:16]}.rollback.tmp"
        )
        if row.prior_state == "ABSENT":
            _rollback_absent_target_at(
                parent_descriptor,
                temporary_name,
                target_name,
                artifact,
                prepared,
            )
        elif row.prior_state == "PRESENT":
            if row.prior_bytes is None or row.prior_mode is None:
                raise WebSolDeploymentApplyError("ROLLBACK_STATE_INVALID")
            if not 0 <= row.prior_mode <= _PERMISSION_BITS_MASK:
                raise WebSolDeploymentApplyError("ROLLBACK_STATE_INVALID")
            _write_exact_temporary_at(
                parent_descriptor,
                temporary_name,
                row.prior_bytes,
                row.prior_mode,
                prepared,
            )
            _rollback_present_target_at(
                parent_descriptor,
                temporary_name,
                target_name,
                row,
                artifact,
                prepared,
            )
        else:
            raise WebSolDeploymentApplyError("ROLLBACK_STATE_INVALID")
    finally:
        os.close(parent_descriptor)

    if not _current_matches_preimage(row, prepared):
        raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN")


def _remove_created_directory(
    directory: Path,
    prepared: PreparedDeployment,
    *,
    effect_unknown_code: str = "ROLLBACK_EFFECT_UNKNOWN",
) -> None:
    if effect_unknown_code not in {
        "APPLY_EFFECT_UNKNOWN",
        "ROLLBACK_EFFECT_UNKNOWN",
    }:
        raise WebSolDeploymentApplyError("PREPARED_INTEGRITY_MISMATCH")
    parent_descriptor = _open_verified_directory(directory.parent, prepared)
    child_descriptor = -1
    try:
        if not _created_directory_matches(
            parent_descriptor, directory.name, prepared
        ):
            raise WebSolDeploymentApplyError(effect_unknown_code)
        try:
            child_descriptor = os.open(
                directory.name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent_descriptor,
            )
        except OSError as exc:
            raise WebSolDeploymentApplyError(effect_unknown_code) from exc
        if not _directory_binding_current(
            child_descriptor, directory, prepared
        ):
            raise WebSolDeploymentApplyError(effect_unknown_code)
        opened = os.fstat(child_descriptor)
        identity = (
            opened.st_dev,
            opened.st_ino,
            opened.st_mode,
            opened.st_nlink,
            opened.st_uid,
            opened.st_gid,
        )
        try:
            if os.listdir(child_descriptor):
                raise WebSolDeploymentApplyError(effect_unknown_code)
        except OSError as exc:
            raise WebSolDeploymentApplyError(effect_unknown_code) from exc
        if not (
            _named_entry_identity_matches(
                parent_descriptor, directory.name, identity
            )
            and _directory_binding_current(
                child_descriptor, directory, prepared
            )
        ):
            raise WebSolDeploymentApplyError(effect_unknown_code)
        try:
            os.rmdir(directory.name, dir_fd=parent_descriptor)
            os.fsync(parent_descriptor)
        except OSError as exc:
            if not _named_entry_absent(parent_descriptor, directory.name):
                raise WebSolDeploymentApplyError(effect_unknown_code) from exc
            try:
                os.fsync(parent_descriptor)
            except OSError as fsync_exc:
                raise WebSolDeploymentApplyError(effect_unknown_code) from fsync_exc
        if not _named_entry_absent(parent_descriptor, directory.name):
            raise WebSolDeploymentApplyError(effect_unknown_code)
        if not _directory_binding_current(
            parent_descriptor, directory.parent, prepared
        ):
            raise WebSolDeploymentApplyError(effect_unknown_code)
    finally:
        if child_descriptor >= 0:
            os.close(child_descriptor)
        os.close(parent_descriptor)


def _abort_partial_apply(
    prepared: PreparedDeployment,
    created_directories: list[Path],
    *,
    preserved_conflicts: set[Path] | None = None,
) -> None:
    """Reconcile one failed apply while preserving unacted foreign targets."""

    preserved = set() if preserved_conflicts is None else set(preserved_conflicts)
    if not preserved.issubset({row.path for row in prepared.preimages}):
        prepared._state = "EFFECT_UNKNOWN"
        raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN")
    artifacts = {
        str(item.destination): item for item in prepared.bundle.artifacts
    }
    try:
        for row in reversed(prepared.preimages):
            artifact = artifacts[str(row.path)]
            temporary = _temporary_path(artifact, prepared)
            parent_descriptor = _open_verified_directory(
                artifact.destination.parent,
                prepared,
            )
            try:
                _cleanup_exact_temporary_at(
                    parent_descriptor,
                    temporary.name,
                    artifact.content,
                    artifact.mode,
                    prepared,
                )
                if row.path in preserved:
                    continue
                if _named_preimage_matches(
                    parent_descriptor,
                    artifact.destination.name,
                    row,
                    prepared,
                ):
                    continue
                if not _named_file_matches(
                    parent_descriptor,
                    artifact.destination.name,
                    artifact.content,
                    artifact.mode,
                    prepared,
                ):
                    raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN")
            finally:
                os.close(parent_descriptor)
            _restore_file(row, artifact, prepared)
        for directory in sorted(
            created_directories,
            key=lambda path: (len(path.parts), str(path)),
            reverse=True,
        ):
            _remove_created_directory(
                directory,
                prepared,
                effect_unknown_code="APPLY_EFFECT_UNKNOWN",
            )
        if (
            any(
                row.path not in preserved
                and not _current_matches_preimage(row, prepared)
                for row in prepared.preimages
            )
            or any(
                not _current_matches_directory_preimage(row, prepared)
                for row in prepared.directory_preimages
            )
        ):
            raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN")
    except WebSolDeploymentApplyError:
        prepared._state = "EFFECT_UNKNOWN"
        raise
    except OSError as exc:
        prepared._state = "EFFECT_UNKNOWN"
        raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN") from exc
    prepared._state = "CONFLICT" if preserved else "ABORTED_ROLLED_BACK"


def rollback_deployment(applied: AppliedDeployment) -> dict[str, object]:
    """Restore every captured preimage once and remove owned empty directories."""

    if not isinstance(applied, AppliedDeployment) or applied._state != "APPLIED":
        raise WebSolDeploymentApplyError("TRANSACTION_CONSUMED")
    prepared = applied.prepared
    try:
        verify_applied_deployment(applied)
        artifacts = {
            str(item.destination): item for item in prepared.bundle.artifacts
        }
        restored = 0
        removed = 0
        changed_paths = set(applied.changed_paths)
        for row in reversed(prepared.preimages):
            if row.path not in changed_paths:
                if not _current_matches_preimage(row, prepared):
                    raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN")
                continue
            _restore_file(row, artifacts[str(row.path)], prepared)
            if row.prior_state == "ABSENT":
                removed += 1
            else:
                restored += 1
        for directory in sorted(
            applied.created_directories,
            key=lambda path: (len(path.parts), str(path)),
            reverse=True,
        ):
            _remove_created_directory(directory, prepared)
        for row in prepared.preimages:
            if not _current_matches_preimage(row, prepared):
                raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN")
    except (WebSolDeploymentApplyError, OSError) as exc:
        applied._state = "EFFECT_UNKNOWN"
        prepared._state = "EFFECT_UNKNOWN"
        if (
            isinstance(exc, WebSolDeploymentApplyError)
            and exc.code == "ROLLBACK_EFFECT_UNKNOWN"
        ):
            raise
        raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN") from exc
    applied._state = "ROLLED_BACK"
    prepared._state = "ROLLED_BACK"
    return {
        "schema": ROLLBACK_RECEIPT_SCHEMA,
        "status": "ROLLBACK_VERIFIED",
        "operation_key": prepared.operation_key,
        "bundle_digest": prepared.bundle.bundle_digest,
        "prepared_digest": prepared.prepared_digest,
        "restored_count": restored,
        "removed_count": removed,
        "production_acceptance_granted": False,
    }


def _current_matches_post_directory(
    row: DirectoryPreimage,
    prepared: PreparedDeployment,
) -> bool:
    try:
        descriptor = _open_verified_directory(row.path, prepared)
    except (OSError, WebSolDeploymentApplyError):
        return False
    try:
        return _directory_binding_current(descriptor, row.path, prepared)
    finally:
        os.close(descriptor)


def _transaction_temporaries_absent(prepared: PreparedDeployment) -> bool:
    for artifact in prepared.bundle.artifacts:
        try:
            descriptor = _open_verified_directory(
                artifact.destination.parent,
                prepared,
            )
        except (OSError, WebSolDeploymentApplyError):
            absent_parents = [
                row
                for row in prepared.directory_preimages
                if row.prior_state == "ABSENT"
                and (
                    row.path == artifact.destination.parent
                    or row.path in artifact.destination.parent.parents
                )
            ]
            if not absent_parents:
                return False
            shallowest = min(
                absent_parents,
                key=lambda row: len(row.path.parts),
            )
            if not _current_matches_directory_preimage(shallowest, prepared):
                return False
            continue
        try:
            apply_temp = _temporary_path(artifact, prepared)
            rollback_temp = artifact.destination.with_name(
                f".{artifact.destination.name}.mmx-"
                f"{prepared.prepared_digest[:16]}.rollback.tmp"
            )
            apply_cleanup = _cleanup_quarantine_name(
                apply_temp.name,
                prepared,
            )
            rollback_cleanup = _cleanup_quarantine_name(
                rollback_temp.name,
                prepared,
            )
            if not (
                _named_entry_absent(descriptor, apply_temp.name)
                and _named_entry_absent(descriptor, rollback_temp.name)
                and _named_entry_absent(descriptor, apply_cleanup)
                and _named_entry_absent(descriptor, rollback_cleanup)
                and _directory_binding_current(
                    descriptor,
                    artifact.destination.parent,
                    prepared,
                )
            ):
                return False
        finally:
            os.close(descriptor)
    return True


def _preimage_complete(prepared: PreparedDeployment) -> bool:
    return (
        all(
            _current_matches_directory_preimage(row, prepared)
            for row in prepared.directory_preimages
        )
        and all(
            _current_matches_preimage(row, prepared)
            for row in prepared.preimages
        )
        and _transaction_temporaries_absent(prepared)
    )


def _postimage_complete(prepared: PreparedDeployment) -> bool:
    return (
        all(
            _current_matches_post_directory(row, prepared)
            for row in prepared.directory_preimages
        )
        and all(
            _current_matches_artifact(artifact, prepared)
            for artifact in prepared.bundle.artifacts
        )
        and _transaction_temporaries_absent(prepared)
    )


def reconcile_prepared_deployment(
    prepared: PreparedDeployment,
) -> AppliedDeployment | None:
    """Classify a persisted PREPARED capsule without repeating any effect."""

    _assert_prepared_integrity(prepared)
    if _preimage_complete(prepared):
        return None
    if not _postimage_complete(prepared):
        prepared._state = "EFFECT_UNKNOWN"
        raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN")

    artifacts = {
        str(item.destination): item for item in prepared.bundle.artifacts
    }
    changed = tuple(
        row.path for row in prepared.plan.changes if row.action != "UNCHANGED"
    )
    if any(str(path) not in artifacts for path in changed):
        prepared._state = "EFFECT_UNKNOWN"
        raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN")
    created = tuple(
        row.path
        for row in prepared.directory_preimages
        if row.prior_state == "ABSENT"
    )
    applied = AppliedDeployment(
        prepared=prepared,
        changed_paths=changed,
        created_directories=created,
        reconciled_paths=changed,
    )
    prepared._state = "APPLIED"
    verify_applied_deployment(applied)
    return applied


def reconcile_applied_rollback(
    applied: AppliedDeployment,
) -> dict[str, object] | None:
    """Reconcile a lost rollback receipt without repeating filesystem effects."""

    if (
        not isinstance(applied, AppliedDeployment)
        or applied._state not in {"APPLIED", "EFFECT_UNKNOWN"}
    ):
        raise WebSolDeploymentApplyError("TRANSACTION_CONSUMED")
    if applied.prepared._state not in {"APPLIED", "EFFECT_UNKNOWN"}:
        raise WebSolDeploymentApplyError("TRANSACTION_CONSUMED")
    _validate_prepared_digest(applied.prepared)
    if _postimage_complete(applied.prepared):
        applied._state = "APPLIED"
        applied.prepared._state = "APPLIED"
        return None
    if not _preimage_complete(applied.prepared):
        applied._state = "EFFECT_UNKNOWN"
        applied.prepared._state = "EFFECT_UNKNOWN"
        raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN")

    changed = set(applied.changed_paths)
    preimages = {row.path: row for row in applied.prepared.preimages}
    if any(path not in preimages for path in changed):
        applied._state = "EFFECT_UNKNOWN"
        applied.prepared._state = "EFFECT_UNKNOWN"
        raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN")
    restored = sum(
        1 for path in changed if preimages[path].prior_state == "PRESENT"
    )
    removed = sum(
        1 for path in changed if preimages[path].prior_state == "ABSENT"
    )
    applied._state = "ROLLED_BACK"
    applied.prepared._state = "ROLLED_BACK"
    return {
        "schema": ROLLBACK_RECEIPT_SCHEMA,
        "status": "ROLLBACK_VERIFIED",
        "operation_key": applied.prepared.operation_key,
        "bundle_digest": applied.prepared.bundle.bundle_digest,
        "prepared_digest": applied.prepared.prepared_digest,
        "restored_count": restored,
        "removed_count": removed,
        "production_acceptance_granted": False,
    }


__all__.extend(
    [
        "APPLY_RECEIPT_SCHEMA",
        "AppliedDeployment",
        "READBACK_RECEIPT_SCHEMA",
        "ROLLBACK_RECEIPT_SCHEMA",
        "apply_deployment",
        "reconcile_applied_rollback",
        "reconcile_prepared_deployment",
        "rollback_deployment",
        "verify_applied_deployment",
    ]
)
