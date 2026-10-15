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
from control_plane.executive_fabric_composition import _bindings
from control_plane.executive_capacity_join import CapacityJoin, PROVIDER_CAPACITY_SCHEMA
from control_plane.executive_host_pressure import HOST_REF_RE
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
                or HOST_REF_RE.fullmatch(physical.host_ref) is None
                or physical.socket_path != FINITE_SOCKET_PATH
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



def render_owner_definition(prior, expected_release_sha: str, join: CapacityJoin) -> dict[str, bytes]:
    """Reproduce the sealed installed worker from the incumbent root source.

    The caller already holds the one original config lock and has verified
    services are stopped, Control/Worker are disarmed and release is selected.
    This function never reads provider credentials, mints Capacity or writes.
    """
    import json
    from control_plane.codex_worker import _assert_binary_unchanged
    from control_plane.model_router import ModelRouter
    from control_plane.worker_execution_contract import BinaryAttestation
    from ops.executive_os.attended_worker_definition import build_finite_worker_artifacts
    from ops.executive_os.finite_service_lifecycle import (
        SYSTEM, PYTHON, ROOT_ID, SOCKET,
    )
    from ops.executive_os.release_manifest import verify

    if (os.geteuid() != 0 or type(join) is not CapacityJoin
            or HOST_REF_RE.fullmatch(join.host_ref) is None
            or type(expected_release_sha) is not str or len(expected_release_sha) != 40
            or any(c not in "0123456789abcdef" for c in expected_release_sha)):
        raise FinitePublicationRefused("sealed root source identity required")
    release = SYSTEM / "releases" / expected_release_sha
    manifest_bytes, _ = owner._read_root_file(
        release / ".executive-release-manifest.json",
        modes=frozenset({0o444}), uid=0, gid=0)
    manifest = json.loads(manifest_bytes)
    if manifest.get("commit_sha") != expected_release_sha:
        raise FinitePublicationRefused("installed release manifest differs")
    verify(release, expected_release_sha, manifest["tree_sha"])

    receipt_path = SYSTEM / "config/claude-minimax-finite-01-attestation.json"
    receipt_bytes, _ = owner._read_root_file(
        receipt_path, modes=frozenset({0o440}), uid=0, gid=470)
    receipt = json.loads(receipt_bytes)
    if (set(receipt) != {"schema_version", "binary"}
            or receipt["schema_version"] != "mastermind.attended_claude_binary/v1"):
        raise FinitePublicationRefused("original binary attestation unavailable")
    binary = BinaryAttestation(**receipt["binary"])
    _assert_binary_unchanged(binary)
    profile = ModelRouter.load().capability_registry.resolve(
        "fabric.attended.claude.bounded.v1")
    try:
        artifacts = build_finite_worker_artifacts(
            primary_config=dict(prior.worker),
            worker_id="minimax-finite-01", worker_user="_mastermind_minimax",
            worker_group="_mastermind_minimax", worker_uid=470, worker_gid=470,
            control_gid=450, runtime_root="/private/var/db/mastermind-executive",
            definition_dir=FINITE_DEFINITION_DIR, socket_path=SOCKET,
            binary=binary, binary_receipt_path=str(receipt_path),
            binary_receipt_sha256=sha256(receipt_bytes), realm_generation=1,
            release_root=str(release), release_commit=expected_release_sha,
            release_tree=manifest["tree_sha"],
            release_manifest_sha256=sha256(manifest_bytes),
            python_binary=PYTHON, host_ref=join.host_ref, model_class="routine",
            execution_profile_digest=profile.profile_digest,
            routing_root_id=ROOT_ID, routing_parent_run_id=ROOT_ID,
            max_turns=2, capacity_capability_id=join.capacity_capability_id)
        if (sha256(artifacts["worker.json"]) != join.worker_source_config_digest
                or set(artifacts) != FILES):
            raise FinitePublicationRefused("Capacity-bound source digest changed")
        verify_candidate(artifacts)
        return artifacts
    except FinitePublicationRefused:
        raise
    except Exception as exc:
        raise FinitePublicationRefused("incumbent sealed renderer refused") from exc


def publish_disarmed_definition(expected_release_sha: str, expected_control_sha256: str,
                                artifacts: dict[str, bytes], *,
                                verified_capacity_binding) -> dict[str, object]:
    """Root-only publication after incumbent Capacity owner binds the proposed identity.

    The callback is an in-process incumbent Capacity owner, never JSON,
    command-line or model input. It confirms the exact original CapacityJoin
    (host, capability and worker source digest), without issuing it.
    Sealed release reproduction is implemented here, not supplied by a caller
    or an external plugin. No new dispatcher or Capacity authority is made.
    """
    hashes = verify_candidate(artifacts)
    if (os.geteuid() != 0 or type(expected_release_sha) is not str
            or len(expected_release_sha) != 40
            or any(c not in "0123456789abcdef" for c in expected_release_sha)
            or type(expected_control_sha256) is not str
            or len(expected_control_sha256) != 64
            or any(c not in "0123456789abcdef" for c in expected_control_sha256)):
        raise FinitePublicationRefused("exact root installed release and config preimage required")
    if not callable(verified_capacity_binding):
        raise FinitePublicationRefused("incumbent Capacity owner is required")
    import json
    physical, = _bindings(artifacts["bindings.json"])
    worker = json.loads(artifacts["worker.json"])
    join = CapacityJoin(physical.host_ref, worker["capacity_capability_id"],
        PROVIDER_CAPACITY_SCHEMA, physical.worker_source_config_digest)
    if verified_capacity_binding(join) is not True:
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
        if (verified_capacity_binding(join) is not True
                or DESTINATION.parent != owner.CONFIG_ROOT):
            raise FinitePublicationRefused("publisher Capacity/config ownership differs")
        # Re-render from the fixed, root-installed release/Capacity identity
        # while the original config-owner lock is held. Caller-supplied bytes
        # do not qualify by satisfying schemas or self-declared hashes.
        expected = render_owner_definition(prior, expected_release_sha, join)
        if expected != artifacts:
            raise FinitePublicationRefused("source-rendered finite definition differs")
        hashes_published = _write_exclusive(DESTINATION, artifacts, uid=0, gid=0)
        if hashes_published != hashes:
            raise FinitePublicationEffectUnknown("sealed bundle mismatch")
        # Original config-owner publication is not itself a full autonomy
        # transaction. A concurrent incumbent modifier must never convert
        # these new files into a false clean receipt. The directory stays in
        # place and the original effect stays UNKNOWN until reconciliation.
        try:
            host.require_exact_install(expected_release_sha)
            host.require_transaction_absent()
            host.require_services_already_stopped()
            host.require_service_uids_quiescent()
            current = host.load_unarmed_configs(expected_release_sha)
            host.require_runtime_quiescent(current)
            host._config_root_safe()
            if (current.control_sha256 != prior.control_sha256
                    or current.worker_sha256 != prior.worker_sha256
                    or verified_capacity_binding(join) is not True):
                raise FinitePublicationEffectUnknown("original postimage changed")
        except Exception as exc:
            raise FinitePublicationEffectUnknown(
                "original config or Capacity changed after finite publication") from exc
        return {"state": "STAGED_DISARMED_DEFINITION", "release": expected_release_sha,
                "control_preimage_sha256": expected_control_sha256,
                "artifacts": hashes_published, "effect": "APPLIED",
                "admitted_worker": False, "service_started": False}
    finally:
        os.close(lock_fd)


def publish_from_installed_sources(expected_release_sha: str,
                                   expected_control_sha256: str,
                                   join: CapacityJoin, *,
                                   verified_capacity_binding) -> dict[str, object]:
    """Single root-owner entry for source-derived, *disarmed* publication.

    The prior-owner checks are intentionally repeated under CONFIG_ROOT lock by
    publish_disarmed_definition. The first phase renders inert bytes only;
    nothing changes until the latter exact-preimage exclusive directory write.
    No imported source may create a CapacityJoin or register a worker.
    """
    if (os.geteuid() != 0 or type(join) is not CapacityJoin
            or not callable(verified_capacity_binding)):
        raise FinitePublicationRefused("root and incumbent Capacity owner required")
    host = owner.ProductionCeoSubmitHost()
    host.require_exact_install(expected_release_sha)
    host.require_transaction_absent()
    host.require_services_already_stopped()
    host.require_service_uids_quiescent()
    prior = host.load_unarmed_configs(expected_release_sha)
    host.require_runtime_quiescent(prior)
    if prior.control_sha256 != expected_control_sha256:
        raise FinitePublicationRefused("Control source preimage changed")
    if verified_capacity_binding(join) is not True:
        raise FinitePublicationRefused("current Capacity join not admitted")
    prepared = render_owner_definition(prior, expected_release_sha, join)
    return publish_disarmed_definition(expected_release_sha,
        expected_control_sha256, prepared,
        verified_capacity_binding=verified_capacity_binding)
