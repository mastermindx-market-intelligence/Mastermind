"""Filesystem observations for the incumbent broker's terminal assignment.

This module owns no run/admission state and performs no chmod, signal or launch.
Its caller must retain the original broker exclusion and a completed UID sweep.
Control performs the actual seal; this worker-side observation checks its exact
original paths and denial. It is not a Linux namespace or UID-census qualifier.
"""
from __future__ import annotations

import errno
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import stat

from control_plane.executive_workspace import _seal_identity


class AssignmentObservationError(RuntimeError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def validate_physical_release(value, *, run_id):
    """Validate retained original LaneReleaseReceipt, never manufacture release.

    Call only on the authenticated original backend's response. Shape and
    digests alone convey no physical ownership, cleanup or account settlement.
    """
    fields = {'schema', 'key', 'marker_device', 'marker_inode', 'parent_device',
              'parent_inode', 'released_at', 'marker_absent', 'parent_synced'}
    if (type(value) is not dict or set(value) != fields
            or value['schema'] != 'mastermind.lane.owned_release/v1'
            or value['key'] != run_id
            or value['marker_absent'] is not True or value['parent_synced'] is not True
            or any(type(value[k]) is not int or value[k] < 0 for k in (
                'marker_device', 'marker_inode', 'parent_device', 'parent_inode'))
            or type(value['released_at']) is not str or not value['released_at']):
        raise AssignmentObservationError('original physical release is unconfirmed')
    return json.loads(canonical(value))


def require_worker_principal(policy):
    if (os.geteuid() != policy.worker_uid or os.getegid() != policy.worker_gid
            or os.getuid() != policy.worker_uid or os.getgid() != policy.worker_gid
            or set(os.getgroups()) - {policy.worker_gid}
            or policy.worker_uid == policy.control_uid):
        raise AssignmentObservationError("assignment observation requires the dedicated worker principal")


def observe_roots(paths, policy, manifest):
    require_worker_principal(policy)
    expected = {
        item["disposition"]: item["identity"]
        for item in manifest["entries"]
        if item["disposition"] in {"CURRENT_WORKSPACE", "CURRENT_RUN"}
    }
    observed = {}
    for label, raw in paths.items():
        path = Path(raw)
        info = path.lstat()
        if (not path.is_absolute() or path.resolve(strict=True) != path
                or not stat.S_ISDIR(info.st_mode) or info.st_uid != policy.control_uid
                or info.st_gid != policy.worker_gid or stat.S_IMODE(info.st_mode) & 0o007):
            raise AssignmentObservationError("assignment is not a protected Control-owned boundary")
        identity = _seal_identity(path, info)
        original = expected.get("CURRENT_" + label.upper(), {})
        # Working inside an assignment may change its mtime, never its root
        # identity or admitted mode. In particular shared run roots are 0770.
        if any(identity[key] != original.get(key) for key in identity if key != "mtime_ns"):
            raise AssignmentObservationError("assignment differs from its admitted launch manifest")
        parent = path.parent
        parent_info = parent.lstat()
        store = policy.workspace_root if label == "workspace" else policy.run_root
        if (parent != store or parent.resolve(strict=True) != parent
                or not stat.S_ISDIR(parent_info.st_mode)
                or parent_info.st_uid != policy.control_uid
                or stat.S_IMODE(parent_info.st_mode) & 0o022):
            raise AssignmentObservationError("assignment parent permits replacement")
        observed[label] = identity
    if set(observed) != {"workspace", "run"}:
        raise AssignmentObservationError("exact workspace and run boundaries required")
    return observed


def _require_denied(path):
    """Test traversal/open/list on the exact root without accepting absence."""
    observations = {}
    for name in ("open", "traverse", "list"):
        fd = None
        try:
            if name == "open":
                fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            elif name == "traverse":
                # Preserve the terminal '/.': Path normalisation would erase it.
                os.stat(str(path) + "/.")
            else:
                with os.scandir(path) as entries:
                    next(entries, None)
        except OSError as exc:
            if exc.errno != errno.EACCES:
                raise AssignmentObservationError("assignment denial is unavailable or ambiguous") from exc
            observations[name] = "EACCES"
        else:
            raise AssignmentObservationError("worker can still access original assignment")
        finally:
            if fd is not None:
                os.close(fd)
    return observations


def validate_control_seal(snapshot, seal, control_uid):
    if (type(seal) is not dict or set(seal) != {
            "schema_version", "sealed_at", "control_uid", "paths", "passed"}
            or seal["schema_version"] != "mastermind.executive_assignment_seal/v1"
            or seal["passed"] is not True or type(seal["control_uid"]) is not int
            or seal["control_uid"] != control_uid
            or type(seal["paths"]) is not dict or set(seal["paths"]) != set(snapshot["paths"])):
        raise AssignmentObservationError("Control seal does not match prepared assignment")
    try:
        stamp = dt.datetime.fromisoformat(seal["sealed_at"])
        if stamp.tzinfo is None:
            raise ValueError()
    except (TypeError, ValueError):
        raise AssignmentObservationError("Control seal timestamp is malformed") from None
    for label, before in snapshot["paths"].items():
        item = seal["paths"][label]
        if (type(item) is not dict or set(item) != {"before", "after", "worker_traversal_revoked"}
                or item["worker_traversal_revoked"] is not True or item["before"] != before
                or type(item["after"]) is not dict or set(item["after"]) != set(before)):
            raise AssignmentObservationError("Control seal preimage differs")
        after = item["after"]
        if (any(type(after[key]) is not int for key in set(after) - {"path"})
                or after["mode"] != 0o700
                or any(after[key] != before[key] for key in ("path", "device", "inode", "uid", "gid"))):
            raise AssignmentObservationError("Control seal changed the assignment identity")


def verify_control_seal(snapshot, seal, policy):
    require_worker_principal(policy)
    validate_control_seal(snapshot, seal, policy.control_uid)
    denial = {}
    for label, before in snapshot["paths"].items():
        after = seal["paths"][label]["after"]
        path = Path(before["path"])
        info = path.lstat()
        actual = _seal_identity(path, info)
        if actual != after or not stat.S_ISDIR(info.st_mode):
            raise AssignmentObservationError("Control seal is not the current original boundary")
        denial[label] = _require_denied(path)
        if _seal_identity(path, path.lstat()) != after:
            raise AssignmentObservationError("original boundary moved during denial observation")
    return denial


def control_retention_record(observation):
    """Payload owned by Supervisor's existing private per-Attempt receipts.

    Producing this value is not retention. Only the authenticated Control owner
    may acknowledge it after its existing durable write and fresh readback.
    """
    return {"schema_version": "mastermind.control_assignment_observation/v1",
            "observation_sha256": digest(observation), "observation": observation}


def verify_control_readback(path, record):
    """Read the original Control owner's private receipt, never a remote path."""
    parent = path.parent.lstat()
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid()
            or stat.S_IMODE(parent.st_mode) & 0o077
            or path.parent.resolve(strict=True) != path.parent):
        raise AssignmentObservationError("Control receipt parent is not private")
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        pinned_parent = os.fstat(directory)
        if (pinned_parent.st_dev, pinned_parent.st_ino) != (parent.st_dev, parent.st_ino):
            raise AssignmentObservationError("Control receipt parent moved")
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                    or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) & 0o077
                    or before.st_size > 1024 * 1024):
                raise AssignmentObservationError("Control receipt is not private bounded evidence")
            # Exact existing bytes may follow a prior interrupted write. Reuse
            # the pinned original descriptors to establish file and directory
            # durability before the fresh readback permits an ACK.
            os.fsync(fd)
            os.fsync(directory)
            raw = bytearray()
            while chunk := os.read(fd, min(8192, 1024 * 1024 + 1 - len(raw))):
                raw.extend(chunk)
                if len(raw) > 1024 * 1024:
                    raise AssignmentObservationError("Control receipt exceeds bound")
            after = os.fstat(fd)
            visible = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
            fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_size", "st_mtime_ns")
            if (any(getattr(before, key) != getattr(after, key) for key in fields)
                    or (visible.st_dev, visible.st_ino) != (before.st_dev, before.st_ino)
                    or _seal_identity(path.parent, path.parent.lstat()) != _seal_identity(path.parent, parent)
                    or bytes(raw) != (json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()):
                raise AssignmentObservationError("Control receipt readback differs")
        finally:
            os.close(fd)
    finally:
        os.close(directory)
