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


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _validate_directory(path: Path, prepared: PreparedDeployment) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise WebSolDeploymentApplyError("DIRECTORY_INVALID") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise WebSolDeploymentApplyError("DIRECTORY_INVALID")
    if info.st_uid != prepared.expected_uid or info.st_gid != prepared.expected_gid:
        raise WebSolDeploymentApplyError("DIRECTORY_OWNER_MISMATCH")
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise WebSolDeploymentApplyError("DIRECTORY_MODE_MISMATCH")


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


def _assert_prepared_integrity(prepared: PreparedDeployment) -> None:
    if not isinstance(prepared, PreparedDeployment):
        raise WebSolDeploymentApplyError("PREPARED_INVALID")
    if prepared._state != "PREPARED":
        raise WebSolDeploymentApplyError("TRANSACTION_CONSUMED")
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


def _assert_prepared(prepared: PreparedDeployment) -> None:
    _assert_prepared_integrity(prepared)
    if any(
        not _current_matches_directory_preimage(row)
        for row in prepared.directory_preimages
    ):
        raise WebSolDeploymentApplyError("PREIMAGE_CONFLICT")
    if any(not _current_matches_preimage(row) for row in prepared.preimages):
        raise WebSolDeploymentApplyError("PREIMAGE_CONFLICT")


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
        if directory.exists() or directory.is_symlink():
            raise WebSolDeploymentApplyError("DIRECTORY_PREIMAGE_CONFLICT")
        try:
            directory.mkdir(mode=0o700)
            created.append(directory)
            _fsync_directory(directory.parent)
        except OSError as exc:
            raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN") from exc
        _validate_directory(directory, prepared)



def _remove_owned_partial_temporary(
    temporary: Path,
    *,
    created_dev: int,
    created_ino: int,
    prepared: PreparedDeployment,
) -> None:
    try:
        info = temporary.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_dev != created_dev
            or info.st_ino != created_ino
            or info.st_uid != prepared.expected_uid
            or info.st_gid != prepared.expected_gid
        ):
            raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN")
        temporary.unlink()
        _fsync_directory(temporary.parent)
    except WebSolDeploymentApplyError:
        raise
    except OSError as exc:
        raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN") from exc


def _write_exact_temporary(
    temporary: Path,
    content: bytes,
    mode: int,
    prepared: PreparedDeployment,
) -> None:
    if type(content) is not bytes or type(mode) is not int or not 0 <= mode <= 0o777:
        raise WebSolDeploymentApplyError("TEMPORARY_INPUT_INVALID")
    if temporary.exists() or temporary.is_symlink():
        raise WebSolDeploymentApplyError("TEMPORARY_PATH_CONFLICT")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600)
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
        _remove_owned_partial_temporary(
            temporary,
            created_dev=created.st_dev,
            created_ino=created.st_ino,
            prepared=prepared,
        )
        raise WebSolDeploymentApplyError("TEMPORARY_WRITE_FAILED") from failure
    if not _temporary_matches(temporary, content, mode, prepared):
        raise WebSolDeploymentApplyError("TEMPORARY_READBACK_MISMATCH")


def _temporary_matches(
    temporary: Path,
    content: bytes,
    mode: int,
    prepared: PreparedDeployment,
) -> bool:
    try:
        info = temporary.lstat()
    except OSError:
        return False
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != prepared.expected_uid
        or info.st_gid != prepared.expected_gid
        or stat.S_IMODE(info.st_mode) != mode
    ):
        return False
    try:
        return temporary.read_bytes() == content
    except OSError:
        return False


def _write_temporary(
    temporary: Path,
    artifact: deployment.DeploymentArtifact,
    prepared: PreparedDeployment,
) -> None:
    _write_exact_temporary(
        temporary,
        artifact.content,
        artifact.mode,
        prepared,
    )


def _temporary_path(artifact: deployment.DeploymentArtifact, prepared: PreparedDeployment) -> Path:
    return artifact.destination.with_name(
        f".{artifact.destination.name}.mmx-{prepared.prepared_digest[:16]}.tmp"
    )


def _cleanup_exact_temporary_bytes(
    temporary: Path,
    content: bytes,
    mode: int,
    prepared: PreparedDeployment,
) -> bool:
    if not (temporary.exists() or temporary.is_symlink()):
        return False
    if not _temporary_matches(temporary, content, mode, prepared):
        raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN")
    temporary.unlink()
    _fsync_directory(temporary.parent)
    return True


def _cleanup_exact_temporary(
    temporary: Path,
    artifact: deployment.DeploymentArtifact,
    prepared: PreparedDeployment,
) -> bool:
    return _cleanup_exact_temporary_bytes(
        temporary,
        artifact.content,
        artifact.mode,
        prepared,
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
            _write_temporary(temporary, artifact, prepared)
            try:
                os.replace(temporary, artifact.destination)
                _fsync_directory(artifact.destination.parent)
            except OSError as exc:
                if not _current_matches_artifact(artifact, prepared):
                    raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN") from exc
                removed = _cleanup_exact_temporary(temporary, artifact, prepared)
                if not removed:
                    _fsync_directory(artifact.destination.parent)
                reconciled.append(artifact.destination)
            if not _current_matches_artifact(artifact, prepared):
                raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN")
            changed.append(artifact.destination)
    except WebSolDeploymentApplyError as exc:
        _abort_partial_apply(prepared, created_directories)
        raise WebSolDeploymentApplyError("APPLY_ABORTED_ROLLED_BACK") from exc
    except OSError as exc:
        _abort_partial_apply(prepared, created_directories)
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
    for artifact in applied.prepared.bundle.artifacts:
        if not _current_matches_artifact(artifact, applied.prepared):
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


def _restore_file(
    row: ArtifactPreimage,
    artifact: deployment.DeploymentArtifact,
    prepared: PreparedDeployment,
) -> None:
    target = row.path
    if row.prior_state == "ABSENT":
        try:
            target.unlink()
            _fsync_directory(target.parent)
        except OSError as exc:
            if target.exists() or target.is_symlink():
                raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN") from exc
        if target.exists() or target.is_symlink():
            raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN")
        return

    if row.prior_bytes is None or row.prior_mode is None:
        raise WebSolDeploymentApplyError("ROLLBACK_STATE_INVALID")
    if not 0 <= row.prior_mode <= 0o777:
        raise WebSolDeploymentApplyError("ROLLBACK_STATE_INVALID")
    temporary = target.with_name(
        f".{target.name}.mmx-{prepared.prepared_digest[:16]}.rollback.tmp"
    )
    _write_exact_temporary(
        temporary,
        row.prior_bytes,
        row.prior_mode,
        prepared,
    )
    try:
        os.replace(temporary, target)
        _fsync_directory(target.parent)
    except OSError as exc:
        if not _current_matches_preimage(row):
            raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN") from exc
        removed = _cleanup_exact_temporary_bytes(
            temporary,
            row.prior_bytes,
            row.prior_mode,
            prepared,
        )
        if not removed:
            _fsync_directory(target.parent)
    if not _current_matches_preimage(row):
        raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN")


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
            _cleanup_exact_temporary(temporary, artifact, prepared)
            if _current_matches_preimage(row):
                continue
            if not _current_matches_artifact(artifact, prepared):
                raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN")
            _restore_file(row, artifact, prepared)
        for directory in sorted(
            created_directories,
            key=lambda path: (len(path.parts), str(path)),
            reverse=True,
        ):
            directory.rmdir()
            _fsync_directory(directory.parent)
        if any(not _current_matches_preimage(row) for row in prepared.preimages):
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
        try:
            directory.rmdir()
            _fsync_directory(directory.parent)
        except OSError as exc:
            raise WebSolDeploymentApplyError("ROLLBACK_EFFECT_UNKNOWN") from exc
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
        and stat.S_IMODE(info.st_mode) == 0o700
    )


def reconcile_prepared_deployment(
    prepared: PreparedDeployment,
) -> AppliedDeployment | None:
    """Classify a persisted PREPARED capsule without repeating any effect.

    ``None`` means every file and directory still matches the captured preimage,
    so the caller may perform the original apply once.  An ``AppliedDeployment``
    means the exact whole postimage is already present and has been reconciled.
    Any mixed or foreign state is effect-unknown and consumes the prepared object.
    """

    _assert_prepared_integrity(prepared)
    exact_preimage = (
        all(
            _current_matches_directory_preimage(row)
            for row in prepared.directory_preimages
        )
        and all(_current_matches_preimage(row) for row in prepared.preimages)
    )
    if exact_preimage:
        return None

    artifacts = {
        str(item.destination): item for item in prepared.bundle.artifacts
    }
    exact_postimage = (
        all(
            _current_matches_post_directory(row, prepared)
            for row in prepared.directory_preimages
        )
        and all(
            _current_matches_artifact(artifact, prepared)
            for artifact in prepared.bundle.artifacts
        )
    )
    for artifact in prepared.bundle.artifacts:
        temporary = _temporary_path(artifact, prepared)
        rollback_temporary = artifact.destination.with_name(
            f".{artifact.destination.name}.mmx-"
            f"{prepared.prepared_digest[:16]}.rollback.tmp"
        )
        if (
            temporary.exists()
            or temporary.is_symlink()
            or rollback_temporary.exists()
            or rollback_temporary.is_symlink()
        ):
            exact_postimage = False
    if not exact_postimage:
        prepared._state = "EFFECT_UNKNOWN"
        raise WebSolDeploymentApplyError("APPLY_EFFECT_UNKNOWN")

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


__all__.extend(
    [
        "APPLY_RECEIPT_SCHEMA",
        "AppliedDeployment",
        "READBACK_RECEIPT_SCHEMA",
        "ROLLBACK_RECEIPT_SCHEMA",
        "apply_deployment",
        "reconcile_prepared_deployment",
        "rollback_deployment",
        "verify_applied_deployment",
    ]
)
