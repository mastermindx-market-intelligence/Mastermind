"""Publish one dormant finite-worker definition through the incumbent config owner.

This writes no credential, provider state, CEO/COO arm, Runtime row or service.
It requires a root-installed release, a stopped/quiescent Control+Worker, and
five exact already-rendered bytes from the selected trusted host/Capacity input.
An interrupted write is EFFECT_UNKNOWN and must be reconciled, never replayed.
"""
from __future__ import annotations

import fcntl
import hashlib
import os
from pathlib import Path
import stat
from collections.abc import Mapping

from ops.executive_os import autonomy_control as owner
from ops.executive_os.attended_worker_definition import build_finite_control_delta
from control_plane.executive_fabric_composition import _bindings, FabricCompositionError
from control_plane.fabric_attended_routing import FINITE_DEFINITION_DIR

FILES = frozenset({
    "worker.json", "bridge.json", "bindings.json", "owner_entry.py",
    "com.mastermind.executive.fabric.minimax-finite-01.plist",
})
DESTINATION = Path(FINITE_DEFINITION_DIR)
MAX_FILE_BYTES = 32_768


class FinitePublicationRefused(ValueError):
    pass


class FinitePublicationEffectUnknown(RuntimeError):
    pass


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def verify_candidate(artifacts: Mapping[str, bytes]) -> dict[str, str]:
    """Verify inert identities before any exclusive filesystem publication."""
    if (type(artifacts) is not dict or set(artifacts) != FILES
            or any(type(v) is not bytes or not 1 <= len(v) <= MAX_FILE_BYTES
                   for v in artifacts.values())):
        raise FinitePublicationRefused("five bounded exact source artifacts required")
    # Use the canonical existing consumer, not a second schema or parser.
    try:
        delta = build_finite_control_delta(
            definition_dir=FINITE_DEFINITION_DIR, worker_artifacts=artifacts)
        physical, = _bindings(artifacts["bindings.json"])
        from control_plane.executive_fabric_bridge_broker import BridgeConfig
        import json
        from control_plane.fabric_attended_routing import FINITE_SOCKET_PATH
        worker = json.loads(artifacts["worker.json"])
        if (type(worker.get("capacity_capability_id")) is not str
                or not worker["capacity_capability_id"]
                or physical.host_ref in {"local-unbound", "placeholder"}
                or physical.socket_path != FINITE_SOCKET_PATH
                or not physical.host_ref
                or physical.worker_source_config_digest != sha256(artifacts["worker.json"])
                or not delta or delta["fabric_bridge_armed"] is not False):
            raise FinitePublicationRefused("Capacity-selected finite owner is incomplete")
        BridgeConfig.from_document(json.loads(artifacts["bridge.json"]))
        import plistlib
        plist = plistlib.loads(artifacts["com.mastermind.executive.fabric.minimax-finite-01.plist"])
        if (plist.get("Label") != "com.mastermind.executive.fabric.minimax-finite-01"
                or plist.get("Disabled") is not True
                or plist.get("RunAtLoad") is not False):
            raise FinitePublicationRefused("finite definition must ship disabled")
    except FinitePublicationRefused:
        raise
    except Exception as exc:
        raise FinitePublicationRefused("finite definition validation refused") from exc
    return {name: sha256(artifacts[name]) for name in sorted(FILES)}


def _write_exclusive(directory: Path, artifacts: Mapping[str, bytes], *,
                     uid: int, gid: int, mode: int = 0o444) -> dict[str, str]:
    """One exclusive directory marker; any subsequent failure leaves it for reconciliation.

    Never remove or republish an uncertain directory. The private initial
    0700 directory prevents other readers from seeing incomplete artifacts.
    """
    verify_candidate(dict(artifacts))
    if directory.exists() or directory.is_symlink():
        raise FinitePublicationRefused("definition already exists, inspect original")
    attempted = False
    try:
        attempted = True
        os.mkdir(directory, 0o700)
        os.chown(directory, uid, gid)
        os.chmod(directory, 0o700)
        for name in sorted(FILES):
            path = directory/name
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), mode)
            try:
                pending = memoryview(artifacts[name])
                while pending:
                    count = os.write(fd, pending)
                    if count <= 0:
                        raise OSError("short artifact write")
                    pending = pending[count:]
                os.fchown(fd, uid, gid)
                os.fchmod(fd, mode)
                os.fsync(fd)
            finally:
                os.close(fd)
        from control_plane.fs_security import has_macos_acl
        observed = {}
        for name in sorted(FILES):
            path = directory/name
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                info, visible = os.fstat(fd), path.lstat()
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid
                        or info.st_gid != gid or stat.S_IMODE(info.st_mode) != mode
                        or info.st_nlink != 1
                        or (info.st_dev, info.st_ino) != (visible.st_dev, visible.st_ino)
                        or has_macos_acl(path, expected_identity=visible)):
                    raise FinitePublicationEffectUnknown("artifact identity or ACL differs")
                body = os.read(fd, MAX_FILE_BYTES + 1)
                if len(body) > MAX_FILE_BYTES or os.read(fd, 1):
                    raise FinitePublicationEffectUnknown("artifact length changed")
                observed[name] = sha256(body)
            finally:
                os.close(fd)
        if observed != {name: sha256(artifacts[name]) for name in FILES}:
            raise FinitePublicationEffectUnknown("artifact postimage differs")
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0))
        try:
            info, visible = os.fstat(descriptor), directory.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != uid
                    or info.st_gid != gid or stat.S_IMODE(info.st_mode) != 0o700
                    or (info.st_dev, info.st_ino) != (visible.st_dev, visible.st_ino)
                    or has_macos_acl(directory, expected_identity=visible)):
                raise FinitePublicationEffectUnknown("definition identity or ACL changed")
            os.fsync(descriptor)
            os.fchmod(descriptor, 0o755)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        parent_fd = os.open(directory.parent, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0))
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        return observed
    except FinitePublicationRefused:
        raise
    except Exception as exc:
        if attempted:
            raise FinitePublicationEffectUnknown("original finite publication may have executed") from exc
        raise


def publish_disarmed_definition(expected_release_sha: str, expected_control_sha256: str,
                                artifacts: dict[str, bytes], *,
                                verified_capacity_binding, trusted_render_again) -> dict[str, object]:
    """Root-only publication after incumbent Capacity owner binds the proposed identity.

    Both callbacks are host-selected, in-process incumbent owners, never JSON,
    command-line or model input. verified_capacity_binding must confirm the
    original current Capacity identity, without issuing it. trusted_render_again
    must reproduce all five bytes from the installed signed source and current
    selected Capacity fact while the original config mutex is held. Neither
    callback is a new dispatcher or Capacity authority.
    """
    hashes = verify_candidate(artifacts)
    if (os.geteuid() != 0 or type(expected_release_sha) is not str
            or len(expected_release_sha) != 40
            or any(c not in "0123456789abcdef" for c in expected_release_sha)
            or type(expected_control_sha256) is not str
            or len(expected_control_sha256) != 64
            or any(c not in "0123456789abcdef" for c in expected_control_sha256)):
        raise FinitePublicationRefused("exact root installed release and config preimage required")
    if not callable(verified_capacity_binding) or not callable(trusted_render_again):
        raise FinitePublicationRefused("incumbent Capacity owner and renderer are required")
    import json
    physical, = _bindings(artifacts["bindings.json"])
    worker = json.loads(artifacts["worker.json"])
    if verified_capacity_binding(physical.host_ref, worker["capacity_capability_id"]) is not True:
        raise FinitePublicationRefused("Capacity owner refused fixed finite identity")
    host = owner.ProductionCeoSubmitHost()
    host.require_exact_install(expected_release_sha)
    host.require_transaction_absent()
    host._config_root_safe()
    lock_fd = os.open(owner.CONFIG_ROOT, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0))
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        held, visible = os.fstat(lock_fd), owner.CONFIG_ROOT.lstat()
        if ((held.st_dev, held.st_ino) != (visible.st_dev, visible.st_ino)):
            raise FinitePublicationRefused("incumbent config owner changed")
        host.require_exact_install(expected_release_sha)
        host.require_transaction_absent()
        host.require_services_already_stopped()
        host.require_service_uids_quiescent()
        prior = host.load_unarmed_configs(expected_release_sha)
        host.require_runtime_quiescent(prior)
        if (prior.control_sha256 != expected_control_sha256
                or any(prior.control.get(k, False) is not False for k in
                       ("ceo_submit_armed", "coo_autonomy_armed",
                        "coo_operator_harness_armed", "fabric_bridge_armed", "coo_foreground_only"))
                or prior.worker.get("operator_harness_armed") is not False):
            raise FinitePublicationRefused("Control and primary Worker must remain disarmed")
        if (verified_capacity_binding(physical.host_ref, worker["capacity_capability_id"]) is not True
                or DESTINATION.parent != owner.CONFIG_ROOT):
            raise FinitePublicationRefused("publisher Capacity/config ownership differs")
        # Re-render from incumbent trusted release/Capacity input while its
        # config-owner lock is held; arbitrary proposed JSON or generated entry
        # bytes never qualify just by satisfying a schema and matching their
        # own public digest.
        expected = trusted_render_again(physical.host_ref, worker["capacity_capability_id"])
        if type(expected) is not dict or set(expected) != FILES or expected != artifacts:
            raise FinitePublicationRefused("source-rendered finite definition differs")
        hashes_published = _write_exclusive(DESTINATION, artifacts, uid=0, gid=0)
        if hashes_published != hashes:
            raise FinitePublicationEffectUnknown("sealed bundle mismatch")
        return {"state": "STAGED_DISARMED_DEFINITION", "release": expected_release_sha,
                "control_preimage_sha256": expected_control_sha256,
                "artifacts": hashes_published, "effect": "APPLIED",
                "admitted_worker": False, "service_started": False}
    finally:
        os.close(lock_fd)
