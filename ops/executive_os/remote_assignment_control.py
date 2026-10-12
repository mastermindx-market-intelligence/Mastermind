"""Finite filesystem effects of the existing authenticated remote Control gateway.

The Worker Broker retains exclusion; the original Supervisor retains evidence
and acknowledges it. This helper owns no assignment inventory, retry or lifecycle.
Its root-managed binding is deliberately absent from installed gateway configs.
"""
from __future__ import annotations

import dataclasses
import os
from pathlib import Path
import re
import stat
from typing import Any, Awaitable, Callable, Mapping

from control_plane.broker_assignment_seal import canonical, digest, validate_control_seal
from control_plane.executive_workspace import _seal_identity, seal_control_owned_paths


class RemoteAssignmentError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class AssignmentControlBinding:
    worker_id: str
    control_uid: int
    control_gid: int
    worker_uid: int
    worker_gid: int
    workspace_root: Path
    run_root: Path

    def __post_init__(self) -> None:
        if (not isinstance(self.worker_id, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,127}", self.worker_id) is None):
            raise RemoteAssignmentError("assignment worker binding is invalid")
        for field in ("control_uid", "control_gid", "worker_uid", "worker_gid"):
            value = getattr(self, field)
            if type(value) is not int or not 0 < value < 2**31:
                raise RemoteAssignmentError("assignment principal binding is invalid")
        if self.control_uid == self.worker_uid or self.control_gid == self.worker_gid:
            raise RemoteAssignmentError("assignment requires distinct principals")
        for field in ("workspace_root", "run_root"):
            path = Path(getattr(self, field))
            if not path.is_absolute() or ".." in path.parts or str(path) == "/":
                raise RemoteAssignmentError("assignment store binding is invalid")
            object.__setattr__(self, field, path)
        if (self.workspace_root == self.run_root
                or self.workspace_root in self.run_root.parents
                or self.run_root in self.workspace_root.parents):
            raise RemoteAssignmentError("assignment stores overlap")

    @classmethod
    def from_wire(cls, value: Any) -> AssignmentControlBinding:
        if type(value) is not dict or set(value) != {field.name for field in dataclasses.fields(cls)}:
            raise RemoteAssignmentError("assignment binding fields differ")
        if any(type(value[key]) is not str for key in ("workspace_root", "run_root")):
            raise RemoteAssignmentError("assignment store binding is invalid")
        return cls(**value)

    def to_wire(self) -> dict[str, Any]:
        return {**dataclasses.asdict(self), "workspace_root": str(self.workspace_root),
                "run_root": str(self.run_root)}

    def paths_for(self, attempt_id: str) -> dict[str, Path]:
        if (type(attempt_id) is not str
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,127}", attempt_id) is None):
            raise RemoteAssignmentError("assignment Attempt is invalid")
        return {"workspace": self.workspace_root / attempt_id,
                "run": self.run_root / attempt_id}

    def observe_stores(self) -> dict[str, dict[str, Any]]:
        if (os.getuid() != self.control_uid or os.geteuid() != self.control_uid
                or os.getgid() != self.control_gid or os.getegid() != self.control_gid):
            raise RemoteAssignmentError("gateway is not the configured Control principal")
        observed = {}
        for label, path in (("workspace", self.workspace_root), ("run", self.run_root)):
            info = path.lstat()
            if (path.resolve(strict=True) != path or not stat.S_ISDIR(info.st_mode)
                    or info.st_uid != self.control_uid or info.st_gid != self.worker_gid
                    or stat.S_IMODE(info.st_mode) != 0o750):
                raise RemoteAssignmentError("assignment store is not protected Control custody")
            observed[label] = _seal_identity(path, info)
        return observed


async def seal_original_assignment(
    binding: AssignmentControlBinding,
    request: Mapping[str, Any],
    broker_call: Callable[[str, Mapping[str, Any]], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    """Seal only the bound original broker assignment; never finalize admission.

    This is called only after gateway mTLS/envelope validation. No path from the
    caller or worker selects the effect: the fixed stores and original Attempt
    determine both roots. Any interrupted/partial effect stays on that Attempt;
    this operation is modifying and is never automatically retried.
    """
    payload = request["broker_request"]
    if (type(payload) is not dict or set(payload) != {"run_id"}
            or payload["run_id"] != request["attempt_id"]
            or request["worker_id"] != binding.worker_id):
        raise RemoteAssignmentError("assignment request differs from original identity")
    paths = binding.paths_for(request["attempt_id"])
    stores = binding.observe_stores()
    prepared = await broker_call("assignment-seal-prepare", payload)
    if type(prepared) is not dict or set(prepared) != {"snapshot", "snapshot_sha256"}:
        raise RemoteAssignmentError("original broker preparation is unavailable")
    snapshot = prepared["snapshot"]
    if (type(snapshot) is not dict or set(snapshot) != {
            "schema_version", "run_id", "job_id", "worker_id", "effective_grant_digest",
            "process_ref", "paths", "uid_sweep"}
            or snapshot["schema_version"] != "mastermind.worker_assignment_seal_prepare/v1"
            or digest(snapshot) != prepared["snapshot_sha256"]
            or snapshot["run_id"] != request["attempt_id"]
            or snapshot["job_id"] != request["job_id"]
            or snapshot["worker_id"] != binding.worker_id
            or type(snapshot["paths"]) is not dict or set(snapshot["paths"]) != set(paths)):
        raise RemoteAssignmentError("original broker preparation differs from envelope")
    from control_plane.executive_worker_broker import uid_sweep_receipt_is_passing
    if (not uid_sweep_receipt_is_passing(snapshot["uid_sweep"])
            or snapshot["uid_sweep"].get("worker_uid") != binding.worker_uid):
        raise RemoteAssignmentError("original broker cleanup is unproven")
    for label, path in paths.items():
        before = snapshot["paths"][label]
        if (type(before) is not dict or before.get("path") != str(path)
                or before.get("uid") != binding.control_uid
                or before.get("gid") != binding.worker_gid):
            raise RemoteAssignmentError("original assignment is outside configured custody")
    if binding.observe_stores() != stores:
        raise RemoteAssignmentError("assignment stores changed during preparation")
    # Two synchronous FD-pinned filesystem effects: no detached to_thread work
    # can survive timeout/disconnection and later be mistaken for cancellation.
    # Original broker admission remains held for the whole transaction.
    seal = seal_control_owned_paths(paths, control_uid=binding.control_uid,
                                    expected_identities=snapshot["paths"])
    validate_control_seal(snapshot, seal, binding.control_uid)
    if binding.observe_stores() != stores:
        raise RemoteAssignmentError("assignment stores changed during seal")
    observation = await broker_call("assignment-seal-commit", {
        "run_id": payload["run_id"], "snapshot_sha256": prepared["snapshot_sha256"], "seal": seal,
    })
    if (type(observation) is not dict or set(observation) != {
            "schema_version", "snapshot", "snapshot_sha256", "control_seal", "worker_denial"}
            or observation["schema_version"] != "mastermind.worker_assignment_seal_commit/v1"
            or canonical(observation["snapshot"]) != canonical(snapshot)
            or observation["snapshot_sha256"] != prepared["snapshot_sha256"]
            or canonical(observation["control_seal"]) != canonical(seal)
            or observation["worker_denial"] != {
                label: {"open": "EACCES", "traverse": "EACCES", "list": "EACCES"}
                for label in paths}):
        raise RemoteAssignmentError("original worker denial observation differs")
    return observation
