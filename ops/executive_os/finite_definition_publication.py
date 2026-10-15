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
import secrets
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


def _object_at(parent_fd: int, name: str):
    """Observe one name without following symlinks, including proved absence."""
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _same_inode(info, held) -> bool:
    return (info is not None and stat.S_ISDIR(info.st_mode)
            and (info.st_dev, info.st_ino) == (held.st_dev, held.st_ino))


def _discard_definitely_private(parent_fd: int, stage_fd: int,
                                stage_name: str, canonical_name: str,
                                uid: int, gid: int) -> bool:
    """Only remove this caller's provably unpublished staging inode.

    The incumbent config-directory lock remains held by our caller. Never
    touch a canonical target or any unfamiliar content in the private inode.
    A failed cleanup leaves the original uncertain stage for inspection.
    """
    try:
        held = os.fstat(stage_fd)
        staged = _object_at(parent_fd, stage_name)
        canonical = _object_at(parent_fd, canonical_name)
        if (not _same_inode(staged, held) or _same_inode(canonical, held)
                or held.st_uid != uid or held.st_gid != gid
                or stat.S_IMODE(held.st_mode) not in {0o700, 0o755}):
            return False
        names = os.listdir(stage_fd)
        if set(names) - FILES:
            return False
        for name in names:
            file_info = _object_at(stage_fd, name)
            if (file_info is None or not stat.S_ISREG(file_info.st_mode)
                    or file_info.st_uid != uid or file_info.st_gid != gid
                    or file_info.st_nlink != 1):
                return False
        for name in sorted(names):
            os.unlink(name, dir_fd=stage_fd)
        os.rmdir(stage_name, dir_fd=parent_fd)
        os.fsync(parent_fd)
        return True
    except OSError:
        return False


def _write_exclusive(directory: Path, artifacts: Mapping[str, bytes], *,
                     uid: int, gid: int, mode: int = 0o444) -> dict[str, str]:
    """Build privately, then publish one verified directory atomically.

    This is a helper called only after the original Control config directory
    mutex has been acquired by the root owner. It never replaces an existing
    name, emulates exclusive rename, or repairs an uncertain canonical write.
    """
    if type(artifacts) is not dict:
        raise FinitePublicationRefused("exact immutable source bundle required")
    sealed = dict(artifacts)  # private snapshot; all member bytes are immutable
    expected = verify_candidate(sealed)
    from control_plane.fs_security import has_macos_acl
    from ops.executive_os.capacity_host_artifacts import _rename_exclusive
    parent_fd = os.open(directory.parent,
        os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0))
    stage_fd = -1
    stage_name = "." + directory.name + "." + str(os.getpid()) + "." + secrets.token_hex(8) + ".stage"
    stage_created = False
    try:
        if _object_at(parent_fd, directory.name) is not None:
            raise FinitePublicationRefused("definition already exists, inspect original")
        # A prior crash can leave an unpublished private inode. That is an
        # original EFFECT_UNKNOWN, not clearance to create a second generation.
        prefix = "." + directory.name + "."
        if any(name.startswith(prefix) and name.endswith(".stage")
               for name in os.listdir(parent_fd)):
            raise FinitePublicationRefused("prior finite private stage requires reconciliation")
        os.mkdir(stage_name, 0o700, dir_fd=parent_fd)
        stage_created = True
        stage_fd = os.open(stage_name,
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd)
        os.fchown(stage_fd, uid, gid)
        os.fchmod(stage_fd, 0o700)
        held = os.fstat(stage_fd)
        if (not _same_inode(_object_at(parent_fd, stage_name), held)
                or (held.st_uid, held.st_gid, stat.S_IMODE(held.st_mode)) != (uid, gid, 0o700)):
            raise FinitePublicationEffectUnknown("private definition inode changed")
        for name in sorted(FILES):
            descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0), mode, dir_fd=stage_fd)
            try:
                pending = memoryview(sealed[name])
                while pending:
                    count = os.write(descriptor, pending)
                    if count <= 0:
                        raise OSError("short artifact write")
                    pending = pending[count:]
                os.fchown(descriptor, uid, gid)
                os.fchmod(descriptor, mode)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        # Observe every file's bytes and ACL on the same open descriptor;
        # the canonical name remains absent until after this succeeds.
        hashes = {}
        for name in sorted(FILES):
            name_path = directory.parent / stage_name / name
            descriptor = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                                 dir_fd=stage_fd)
            try:
                info, listed = os.fstat(descriptor), _object_at(stage_fd, name)
                if (listed is None or not stat.S_ISREG(info.st_mode)
                        or (info.st_dev, info.st_ino) != (listed.st_dev, listed.st_ino)
                        or info.st_uid != uid or info.st_gid != gid or info.st_nlink != 1
                        or stat.S_IMODE(info.st_mode) != mode
                        or has_macos_acl(name_path, expected_identity=listed,
                                         descriptor=descriptor)):
                    raise FinitePublicationEffectUnknown("private artifact identity or ACL differs")
                chunks, count = [], 0
                while True:
                    part = os.read(descriptor, min(8192, MAX_FILE_BYTES + 1 - count))
                    if not part:
                        break
                    count += len(part)
                    if count > MAX_FILE_BYTES:
                        raise FinitePublicationEffectUnknown("private artifact exceeds bound")
                    chunks.append(part)
                if b"".join(chunks) != sealed[name]:
                    raise FinitePublicationEffectUnknown("private artifact bytes differ")
                hashes[name] = sha256(sealed[name])
            finally:
                os.close(descriptor)
        if hashes != expected or set(os.listdir(stage_fd)) != FILES:
            raise FinitePublicationEffectUnknown("private bundle postimage differs")
        staged = _object_at(parent_fd, stage_name)
        held = os.fstat(stage_fd)
        if (not _same_inode(staged, held) or held.st_uid != uid
                or held.st_gid != gid or stat.S_IMODE(held.st_mode) != 0o700
                or has_macos_acl(directory.parent / stage_name, expected_identity=staged,
                                 descriptor=stage_fd)):
            raise FinitePublicationEffectUnknown("private directory identity or ACL differs")
        os.fsync(stage_fd)
        # The finite bridge's non-root principal must be able to traverse the
        # directory and read the root-owned 0444 definitions at startup. Those
        # nonsecret modes are required by its exact installed reader and the
        # separately reviewed root-owned lifecycle source.
        os.fchmod(stage_fd, 0o755)
        os.fsync(stage_fd)
        if _object_at(parent_fd, directory.name) is not None:
            raise FinitePublicationRefused("canonical finite definition appeared")
        _rename_exclusive(parent_fd, stage_name, parent_fd, directory.name)
        os.fsync(parent_fd)
        actual = _object_at(parent_fd, directory.name)
        if (not _same_inode(actual, held) or actual.st_uid != uid
                or actual.st_gid != gid or stat.S_IMODE(actual.st_mode) != 0o755
                or _object_at(parent_fd, stage_name) is not None):
            raise FinitePublicationEffectUnknown("published exact inode unconfirmed")
        return expected
    except Exception as exc:
        if stage_created and stage_fd >= 0 and _discard_definitely_private(
                parent_fd, stage_fd, stage_name, directory.name, uid, gid):
            raise FinitePublicationRefused(
                "finite private stage refused without canonical publication") from exc
        if not stage_created:
            if isinstance(exc, FinitePublicationRefused):
                raise
            raise FinitePublicationRefused("finite prepublication qualification refused") from exc
        raise FinitePublicationEffectUnknown(
            "original finite directory publication effect unconfirmed") from exc
    finally:
        if stage_fd >= 0:
            os.close(stage_fd)
        os.close(parent_fd)


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
    """One incumbent root/Capacity-gated publication with exact source readback.

    Trusted host code selects the callback. No request, config file, plugin or
    model selects source code or a worker. No new scheduler or lifecycle owner.
    """
    if (os.geteuid() != 0 or type(expected_release_sha) is not str
            or len(expected_release_sha) != 40
            or any(c not in "0123456789abcdef" for c in expected_release_sha)
            or type(expected_control_sha256) is not str
            or len(expected_control_sha256) != 64
            or any(c not in "0123456789abcdef" for c in expected_control_sha256)):
        raise FinitePublicationRefused("exact root release and Control preimage required")
    if not callable(verified_capacity_binding):
        raise FinitePublicationRefused("incumbent Capacity owner is required")
    if type(artifacts) is not dict:
        raise FinitePublicationRefused("exact source bundle required")
    # Never publish from the caller's mutable mapping after validating a copy.
    # Every member must be immutable bytes, not an externally owned bytearray.
    sealed = dict(artifacts)
    hashes = verify_candidate(sealed)
    import json
    physical, = _bindings(sealed["bindings.json"])
    worker = json.loads(sealed["worker.json"])
    join = CapacityJoin(physical.host_ref, worker["capacity_capability_id"],
                        PROVIDER_CAPACITY_SCHEMA, physical.worker_source_config_digest)
    host = owner.ProductionCeoSubmitHost()
    lock_fd = -1
    effect_possible = False
    try:
        host.require_exact_install(expected_release_sha)
        host.require_transaction_absent()
        host._config_root_safe()
        lock_fd = os.open(owner.CONFIG_ROOT,
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0))
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise FinitePublicationRefused(
                "incumbent Control publication mutex occupied") from exc
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
        if (DESTINATION.parent != owner.CONFIG_ROOT
                or verified_capacity_binding(join) is not True):
            raise FinitePublicationRefused("incumbent Capacity/config binding differs")
        # Signed-source reproduction is committed under the SAME mutex.
        expected = render_owner_definition(prior, expected_release_sha, join)
        if expected != sealed:
            raise FinitePublicationRefused("source-rendered finite definition differs")
        effect_possible = True
        hashes_published = _write_exclusive(DESTINATION, sealed, uid=0, gid=0)
        if hashes_published != hashes:
            raise FinitePublicationEffectUnknown("sealed bundle mismatch")
        # Preserve the original effect state on any post-publication drift.
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
            raise FinitePublicationEffectUnknown("original config/Capacity postimage changed")
        return {"state": "STAGED_DISARMED_DEFINITION", "release": expected_release_sha,
                "control_preimage_sha256": expected_control_sha256,
                "artifacts": hashes_published, "effect": "APPLIED",
                "admitted_worker": False, "service_started": False}
    except FinitePublicationRefused:
        raise
    except FinitePublicationEffectUnknown:
        raise
    except Exception as exc:
        if effect_possible:
            raise FinitePublicationEffectUnknown(
                "original finite publication effect unconfirmed") from exc
        raise FinitePublicationRefused("original Control/Capacity qualification refused") from exc
    finally:
        if lock_fd >= 0:
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
    try:
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
    except FinitePublicationRefused:
        raise
    except Exception as exc:
        raise FinitePublicationRefused("original root/Capacity source preflight refused") from exc
    return publish_disarmed_definition(expected_release_sha,
        expected_control_sha256, prepared,
        verified_capacity_binding=verified_capacity_binding)
