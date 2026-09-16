"""Transactional filesystem application for one reviewed Web-Sol deployment bundle.

The existing :mod:`web_sol_deployment` module remains the pure renderer and
planner.  This module owns only the bounded local filesystem transaction used by
the separate INSTALL1 proof carrier.  It performs no browser, profile, account,
credential, network, provider, Runtime, or lifecycle action.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

from . import web_sol_deployment as deployment

PREPARED_RECEIPT_SCHEMA = "mastermind.web_sol_deployment_prepared_receipt.v1"

_OPERATION_RE = re.compile(r"\A[a-z0-9][a-z0-9-]{0,127}\Z")

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


def _prepared_digest_from_state(
    *,
    operation_key: str,
    bundle: deployment.DeploymentBundle,
    plan: deployment.DeploymentPlan,
    expected_uid: int,
    expected_gid: int,
    preimages: tuple[ArtifactPreimage, ...] | list[ArtifactPreimage],
    directory_preimages: tuple[DirectoryPreimage, ...] | list[DirectoryPreimage],
) -> str:
    try:
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

    preimages: list[ArtifactPreimage] = []
    digest_rows: list[dict[str, object]] = []
    for artifact in artifacts:
        target = artifact.destination
        change = rows[str(target)]
        if change.next_sha256 != artifact.sha256 or change.mode != artifact.mode:
            raise WebSolDeploymentApplyError("PLAN_MISMATCH")
        try:
            info = target.lstat()
        except FileNotFoundError:
            info = None
        except OSError as exc:
            raise WebSolDeploymentApplyError("TARGET_READ_FAILED") from exc

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
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise WebSolDeploymentApplyError("TARGET_SYMLINK_REFUSED")
            if info.st_uid != expected_uid or info.st_gid != expected_gid:
                raise WebSolDeploymentApplyError("TARGET_OWNER_MISMATCH")
            try:
                content = target.read_bytes()
            except OSError as exc:
                raise WebSolDeploymentApplyError("TARGET_READ_FAILED") from exc
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
        digest_rows.append(
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

    prepared_digest = _prepared_digest_from_state(
        operation_key=operation,
        bundle=bundle,
        plan=plan,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
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
        prepared_digest=prepared_digest,
    )


__all__ = [
    "ArtifactPreimage",
    "DirectoryPreimage",
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


def _current_matches_directory_preimage(row: DirectoryPreimage) -> bool:
    try:
        info = row.path.lstat()
    except FileNotFoundError:
        return row.prior_state == "ABSENT"
    except OSError:
        return False
    if row.prior_state != "PRESENT":
        return False
    return (
        stat.S_ISDIR(info.st_mode)
        and not stat.S_ISLNK(info.st_mode)
        and info.st_dev == row.prior_dev
        and info.st_ino == row.prior_ino
        and stat.S_IMODE(info.st_mode) == row.prior_mode
        and info.st_uid == row.prior_uid
        and info.st_gid == row.prior_gid
    )


def _current_matches_preimage(row: ArtifactPreimage) -> bool:
    try:
        info = row.path.lstat()
    except FileNotFoundError:
        return row.prior_state == "ABSENT"
    except OSError:
        return False
    if row.prior_state != "PRESENT":
        return False
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        return False
    if (
        info.st_uid != row.prior_uid
        or info.st_gid != row.prior_gid
        or stat.S_IMODE(info.st_mode) != row.prior_mode
    ):
        return False
    try:
        return row.path.read_bytes() == row.prior_bytes
    except OSError:
        return False


def _current_matches_artifact(
    artifact: deployment.DeploymentArtifact,
    prepared: PreparedDeployment,
) -> bool:
    try:
        info = artifact.destination.lstat()
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        return False
    if (
        info.st_uid != prepared.expected_uid
        or info.st_gid != prepared.expected_gid
        or stat.S_IMODE(info.st_mode) != artifact.mode
    ):
        return False
    try:
        return artifact.destination.read_bytes() == artifact.content
    except OSError:
        return False


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
        not _current_matches_directory_preimage(row)
        for row in prepared.directory_preimages
    ):
        raise WebSolDeploymentApplyError("PREIMAGE_CONFLICT")
    if any(not _current_matches_preimage(row) for row in prepared.preimages):
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
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_dev != created_dev
            or info.st_ino != created_ino
            or info.st_uid != prepared.expected_uid
            or info.st_gid != prepared.expected_gid
        ):
            raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN")
        os.unlink(name, dir_fd=parent_descriptor)
        os.fsync(parent_descriptor)
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


def _cleanup_exact_temporary_at(
    parent_descriptor: int,
    name: str,
    content: bytes,
    mode: int,
    prepared: PreparedDeployment,
) -> bool:
    try:
        os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN") from exc
    if not _named_file_matches(parent_descriptor, name, content, mode, prepared):
        raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN")
    try:
        os.unlink(name, dir_fd=parent_descriptor)
        os.fsync(parent_descriptor)
    except OSError as exc:
        raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN") from exc
    return True


def _temporary_path(artifact: deployment.DeploymentArtifact, prepared: PreparedDeployment) -> Path:
    return artifact.destination.with_name(
        f".{artifact.destination.name}.mmx-{prepared.prepared_digest[:16]}.tmp"
    )


def apply_deployment(prepared: PreparedDeployment) -> AppliedDeployment:
    """Apply one prepared bundle exactly once and verify every postimage."""

    _assert_prepared(prepared)
    created_directories: list[Path] = []
    artifacts = {
        str(item.destination): item for item in prepared.bundle.artifacts
    }
    changes = {str(item.path): item for item in prepared.plan.changes}
    changed: list[Path] = []
    reconciled: list[Path] = []

    try:
        _create_parent_directories(prepared, created_directories)
        for row in prepared.preimages:
            artifact = artifacts[str(row.path)]
            change = changes[str(row.path)]
            if change.action == "UNCHANGED":
                if not _current_matches_artifact(artifact, prepared):
                    raise WebSolDeploymentApplyError("READBACK_MISMATCH")
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
                try:
                    os.replace(
                        temporary_name,
                        target_name,
                        src_dir_fd=parent_descriptor,
                        dst_dir_fd=parent_descriptor,
                    )
                    os.fsync(parent_descriptor)
                except OSError as exc:
                    if not _named_file_matches(
                        parent_descriptor,
                        target_name,
                        artifact.content,
                        artifact.mode,
                        prepared,
                    ):
                        raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN") from exc
                    removed = _cleanup_exact_temporary_at(
                        parent_descriptor,
                        temporary_name,
                        artifact.content,
                        artifact.mode,
                        prepared,
                    )
                    if not removed:
                        os.fsync(parent_descriptor)
                    reconciled.append(artifact.destination)
                if not _named_file_matches(
                    parent_descriptor,
                    target_name,
                    artifact.content,
                    artifact.mode,
                    prepared,
                ):
                    raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN")
            finally:
                os.close(parent_descriptor)
            if not _current_matches_artifact(artifact, prepared):
                raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN")
            changed.append(artifact.destination)
    except (WebSolDeploymentApplyError, OSError) as exc:
        try:
            _abort_partial_apply(prepared, created_directories)
        except (WebSolDeploymentApplyError, OSError) as abort_exc:
            prepared._state = "EFFECT_UNKNOWN"
            raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN") from abort_exc
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

        if row.prior_state == "ABSENT":
            try:
                os.unlink(target_name, dir_fd=parent_descriptor)
                os.fsync(parent_descriptor)
            except OSError as exc:
                if not _named_entry_absent(parent_descriptor, target_name):
                    raise WebSolDeploymentApplyError(
                        "ROLLBACK_EFFECT_UNKNOWN"
                    ) from exc
                try:
                    os.fsync(parent_descriptor)
                except OSError as fsync_exc:
                    raise WebSolDeploymentApplyError(
                        "ROLLBACK_EFFECT_UNKNOWN"
                    ) from fsync_exc
            if not _named_entry_absent(parent_descriptor, target_name):
                raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN")
        else:
            if row.prior_bytes is None or row.prior_mode is None:
                raise WebSolDeploymentApplyError("ROLLBACK_STATE_INVALID")
            if not 0 <= row.prior_mode <= _PERMISSION_BITS_MASK:
                raise WebSolDeploymentApplyError("ROLLBACK_STATE_INVALID")
            temporary_name = (
                f".{target.name}.mmx-{prepared.prepared_digest[:16]}.rollback.tmp"
            )
            _write_exact_temporary_at(
                parent_descriptor,
                temporary_name,
                row.prior_bytes,
                row.prior_mode,
                prepared,
            )
            try:
                os.replace(
                    temporary_name,
                    target_name,
                    src_dir_fd=parent_descriptor,
                    dst_dir_fd=parent_descriptor,
                )
                os.fsync(parent_descriptor)
            except OSError as exc:
                if not _named_preimage_matches(
                    parent_descriptor,
                    target_name,
                    row,
                    prepared,
                ):
                    raise WebSolDeploymentApplyError(
                        "ROLLBACK_EFFECT_UNKNOWN"
                    ) from exc
                removed = _cleanup_exact_temporary_at(
                    parent_descriptor,
                    temporary_name,
                    row.prior_bytes,
                    row.prior_mode,
                    prepared,
                )
                if not removed:
                    try:
                        os.fsync(parent_descriptor)
                    except OSError as fsync_exc:
                        raise WebSolDeploymentApplyError(
                            "ROLLBACK_EFFECT_UNKNOWN"
                        ) from fsync_exc
            if not _named_preimage_matches(
                parent_descriptor,
                target_name,
                row,
                prepared,
            ):
                raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN")
    finally:
        os.close(parent_descriptor)

    if not _current_matches_preimage(row):
        raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN")


def _remove_created_directory(
    directory: Path,
    prepared: PreparedDeployment,
) -> None:
    parent_descriptor = _open_verified_directory(directory.parent, prepared)
    child_descriptor = -1
    try:
        if not _created_directory_matches(
            parent_descriptor, directory.name, prepared
        ):
            raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN")
        try:
            child_descriptor = os.open(
                directory.name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent_descriptor,
            )
        except OSError as exc:
            raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN") from exc
        if not _directory_binding_current(
            child_descriptor, directory, prepared
        ):
            raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN")
        try:
            if os.listdir(child_descriptor):
                raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN")
        except OSError as exc:
            raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN") from exc
        try:
            os.rmdir(directory.name, dir_fd=parent_descriptor)
            os.fsync(parent_descriptor)
        except OSError as exc:
            if not _named_entry_absent(parent_descriptor, directory.name):
                raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN") from exc
            try:
                os.fsync(parent_descriptor)
            except OSError as fsync_exc:
                raise WebSolDeploymentApplyError(
                    "ROLLBACK_EFFECT_UNKNOWN"
                ) from fsync_exc
        if not _named_entry_absent(parent_descriptor, directory.name):
            raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN")
        if not _directory_binding_current(
            parent_descriptor, directory.parent, prepared
        ):
            raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN")
    finally:
        if child_descriptor >= 0:
            os.close(child_descriptor)
        os.close(parent_descriptor)


def _abort_partial_apply(
    prepared: PreparedDeployment,
    created_directories: list[Path],
) -> None:
    """Reconcile one failed apply and restore every exact preimage once."""

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
            _remove_created_directory(directory, prepared)
        if (
            any(not _current_matches_preimage(row) for row in prepared.preimages)
            or any(
                not _current_matches_directory_preimage(row)
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
    prepared._state = "ABORTED_ROLLED_BACK"


def rollback_deployment(applied: AppliedDeployment) -> dict[str, object]:
    """Restore every captured preimage once and remove owned empty directories."""

    if not isinstance(applied, AppliedDeployment) or applied._state != "APPLIED":
        raise WebSolDeploymentApplyError("TRANSACTION_CONSUMED")
    verify_applied_deployment(applied)
    artifacts = {
        str(item.destination): item for item in applied.prepared.bundle.artifacts
    }
    restored = 0
    removed = 0
    changed_paths = set(applied.changed_paths)
    for row in reversed(applied.prepared.preimages):
        if row.path not in changed_paths:
            if not _current_matches_preimage(row):
                raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN")
            continue
        _restore_file(row, artifacts[str(row.path)], applied.prepared)
        if row.prior_state == "ABSENT":
            removed += 1
        else:
            restored += 1
    for directory in sorted(
        applied.created_directories,
        key=lambda path: (len(path.parts), str(path)),
        reverse=True,
    ):
        _remove_created_directory(directory, applied.prepared)
    for row in applied.prepared.preimages:
        if not _current_matches_preimage(row):
            raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN")
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


def _current_matches_post_directory(
    row: DirectoryPreimage,
    prepared: PreparedDeployment,
) -> bool:
    if row.prior_state == "PRESENT":
        return _current_matches_directory_preimage(row)
    try:
        info = row.path.lstat()
    except OSError:
        return False
    return (
        stat.S_ISDIR(info.st_mode)
        and not stat.S_ISLNK(info.st_mode)
        and info.st_uid == prepared.expected_uid
        and info.st_gid == prepared.expected_gid
        and stat.S_IMODE(info.st_mode) == _PRIVATE_DIRECTORY_MODE
    )


def _transaction_temporaries_absent(prepared: PreparedDeployment) -> bool:
    for artifact in prepared.bundle.artifacts:
        apply_temp = _temporary_path(artifact, prepared)
        rollback_temp = artifact.destination.with_name(
            f".{artifact.destination.name}.mmx-"
            f"{prepared.prepared_digest[:16]}.rollback.tmp"
        )
        if (
            apply_temp.exists()
            or apply_temp.is_symlink()
            or rollback_temp.exists()
            or rollback_temp.is_symlink()
        ):
            return False
    return True


def _preimage_complete(prepared: PreparedDeployment) -> bool:
    return (
        all(
            _current_matches_directory_preimage(row)
            for row in prepared.directory_preimages
        )
        and all(_current_matches_preimage(row) for row in prepared.preimages)
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

    if not isinstance(applied, AppliedDeployment) or applied._state != "APPLIED":
        raise WebSolDeploymentApplyError("TRANSACTION_CONSUMED")
    if applied.prepared._state != "APPLIED":
        raise WebSolDeploymentApplyError("TRANSACTION_CONSUMED")
    _validate_prepared_digest(applied.prepared)
    if _postimage_complete(applied.prepared):
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
