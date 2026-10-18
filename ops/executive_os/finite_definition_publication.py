"""Publish one dormant finite-worker definition through the incumbent config owner.

This writes no credential, provider state, CEO/COO arm, Runtime row or service.
It requires a root-installed release, a stopped/quiescent Control+Worker, and
five exact rendered artifacts from the selected trusted host/Capacity input.
An interrupted write is EFFECT_UNKNOWN and must be reconciled, never replayed.
"""
from __future__ import annotations

from contextlib import ExitStack
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
from control_plane.executive_capacity_join import CapacityJoin, CapacityJoinError, PROVIDER_CAPACITY_SCHEMA
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
        # This structural check grants neither source acceptance nor enrollment.
        # Native generation/source joins are checked by the locked native owner.
        if "native_capacity_enrollment" in worker:
            from ops.executive_os.capacity_source_contract import validate_native_subscription_capacity_enrollment
            native = validate_native_subscription_capacity_enrollment(worker["native_capacity_enrollment"])
            from control_plane.native_capacity_v2 import TOKEN
            if (native["enrollment_state"] != "unenrolled"
                    or native["host_ref"] != physical.host_ref
                    or type(worker.get("capacity_capability_id")) is not str
                    or TOKEN.fullmatch(worker["capacity_capability_id"]) is None):
                raise FinitePublicationRefused("initial native definition must remain unenrolled")
        else:
            CapacityJoin(physical.host_ref, worker["capacity_capability_id"],
                PROVIDER_CAPACITY_SCHEMA, physical.worker_source_config_digest)
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


def _trusted_control_root(lock_fd: int) -> os.stat_result:
    """Reprove trust on the original CONFIG_ROOT lock descriptor itself."""
    from control_plane.fs_security import has_macos_acl

    held, visible = os.fstat(lock_fd), owner.CONFIG_ROOT.lstat()
    if (not stat.S_ISDIR(held.st_mode)
            or held.st_uid != 0 or held.st_gid != 0
            or stat.S_IMODE(held.st_mode) != 0o755
            or (held.st_dev, held.st_ino) != (visible.st_dev, visible.st_ino)
            or has_macos_acl(owner.CONFIG_ROOT, expected_identity=visible,
                             descriptor=lock_fd)):
        raise FinitePublicationRefused("incumbent Control config root is untrusted")
    return held


def _require_definition_absent(parent_fd: int, name: str) -> None:
    if _object_at(parent_fd, name) is not None:
        raise FinitePublicationRefused("definition already exists, inspect original")
    prefix = "." + name + "."
    if any(value.startswith(prefix) and value.endswith(".stage")
           for value in os.listdir(parent_fd)):
        raise FinitePublicationRefused("prior finite private stage requires reconciliation")


def _write_exclusive(directory: Path, artifacts: Mapping[str, bytes], *,
                     uid: int, gid: int, mode: int = 0o444,
                     parent_fd: int | None = None) -> dict[str, str]:
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
    owns_parent_fd = parent_fd is None
    if owns_parent_fd:
        parent_fd = os.open(directory.parent,
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0))
    if not isinstance(parent_fd, int):
        raise FinitePublicationRefused("original locked parent is unavailable")
    stage_fd = -1
    stage_name = "." + directory.name + "." + str(os.getpid()) + "." + secrets.token_hex(8) + ".stage"
    stage_created = False
    try:
        # In production, parent_fd IS the trusted CONFIG_ROOT lock FD.
        # Never open a second path after the owner has already qualified it.
        held_parent, visible_parent = os.fstat(parent_fd), directory.parent.lstat()
        if (not _same_inode(visible_parent, held_parent)
                or (held_parent.st_uid, held_parent.st_gid,
                    stat.S_IMODE(held_parent.st_mode))
                != (visible_parent.st_uid, visible_parent.st_gid,
                    stat.S_IMODE(visible_parent.st_mode))):
            raise FinitePublicationRefused("original locked parent directory moved")
        _require_definition_absent(parent_fd, directory.name)
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
                observed = b"".join(chunks)
                if observed != sealed[name]:
                    raise FinitePublicationEffectUnknown("private artifact bytes differ")
                hashes[name] = sha256(observed)
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
        return hashes
    except Exception as exc:
        # An FD-limit failure after mkdir but before opening the private
        # stage cannot have issued the canonical rename. Prove the target
        # absent, then remove only this exact still-empty stage.
        if stage_created and stage_fd < 0:
            try:
                staged = _object_at(parent_fd, stage_name)
                if (staged is not None and stat.S_ISDIR(staged.st_mode)
                        and stat.S_IMODE(staged.st_mode) == 0o700
                        and _object_at(parent_fd, directory.name) is None):
                    os.rmdir(stage_name, dir_fd=parent_fd)
                    os.fsync(parent_fd)
                    raise FinitePublicationRefused(
                        "original empty private stage removed before publication") from exc
            except OSError:
                pass
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
        # Final close errors must not mask APPLIED or EFFECT_UNKNOWN.
        if stage_fd >= 0:
            try:
                os.close(stage_fd)
            except OSError:
                pass
        if owns_parent_fd:
            try:
                os.close(parent_fd)
            except OSError:
                pass


def _render_owner_definition(prior, expected_release_sha: str, *, host_ref: str,
                             capacity_capability_id: str,
                             native_capacity_enrollment=None) -> dict[str, bytes]:
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

    if (os.geteuid() != 0 or type(host_ref) is not str
            or HOST_REF_RE.fullmatch(host_ref) is None
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
            python_binary=PYTHON, host_ref=host_ref, model_class="routine",
            execution_profile_digest=profile.profile_digest,
            routing_root_id=ROOT_ID, routing_parent_run_id=ROOT_ID,
            max_turns=2, capacity_capability_id=capacity_capability_id,
            native_capacity_enrollment=native_capacity_enrollment)
        verify_candidate(artifacts)
        return artifacts
    except FinitePublicationRefused:
        raise
    except Exception as exc:
        raise FinitePublicationRefused("incumbent sealed renderer refused") from exc


def render_owner_definition(prior, expected_release_sha: str, join: CapacityJoin) -> dict[str, bytes]:
    """Retain the original legacy join and exact source digest contract."""
    if type(join) is not CapacityJoin:
        raise FinitePublicationRefused("sealed root source identity required")
    artifacts = _render_owner_definition(prior, expected_release_sha,
        host_ref=join.host_ref, capacity_capability_id=join.capacity_capability_id)
    if sha256(artifacts["worker.json"]) != join.worker_source_config_digest:
        raise FinitePublicationRefused("Capacity-bound source digest changed")
    return artifacts


def _require_publication_inputs(expected_release_sha, expected_control_sha256):
    if (os.geteuid() != 0 or type(expected_release_sha) is not str
            or len(expected_release_sha) != 40
            or any(c not in "0123456789abcdef" for c in expected_release_sha)
            or type(expected_control_sha256) is not str
            or len(expected_control_sha256) != 64
            or any(c not in "0123456789abcdef" for c in expected_control_sha256)):
        raise FinitePublicationRefused("exact root release and Control preimage required")


def _publish_selected_definition(expected_release_sha, expected_control_sha256, prepare_locked):
    """The original publication interval, shared by two closed preparations."""
    _require_publication_inputs(expected_release_sha, expected_control_sha256)
    host = owner.ProductionCeoSubmitHost()
    lock_fd = -1
    effect_possible = False
    try:
        with ExitStack() as custody:
            host.require_exact_install(expected_release_sha)
            host.require_transaction_absent()
            host._config_root_safe()
            lock_fd = os.open(owner.CONFIG_ROOT,
                os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0))
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise FinitePublicationRefused("incumbent Control publication mutex occupied") from exc
            _trusted_control_root(lock_fd)
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
            if DESTINATION.parent != owner.CONFIG_ROOT:
                raise FinitePublicationRefused("incumbent Capacity/config binding differs")
            sealed, recheck = prepare_locked(prior, lock_fd, custody)
            hashes = verify_candidate(sealed)
            _trusted_control_root(lock_fd)
            effect_possible = True
            try:
                hashes_published = _write_exclusive(DESTINATION, sealed, uid=0, gid=0,
                                                    parent_fd=lock_fd)
            except FinitePublicationRefused:
                # Only this incumbent writer can prove its stage never became
                # canonical and that its own private cleanup completed.
                effect_possible = False
                raise
            if hashes_published != hashes:
                raise FinitePublicationEffectUnknown("published disk digest differs")
            host.require_exact_install(expected_release_sha)
            host.require_transaction_absent()
            host.require_services_already_stopped()
            host.require_service_uids_quiescent()
            current = host.load_unarmed_configs(expected_release_sha)
            host.require_runtime_quiescent(current)
            host._config_root_safe()
            _trusted_control_root(lock_fd)
            if (current.control_sha256 != prior.control_sha256
                    or current.worker_sha256 != prior.worker_sha256):
                raise FinitePublicationEffectUnknown("original config/Capacity postimage changed")
            recheck(current)
            return {"state": "STAGED_DISARMED_DEFINITION", "release": expected_release_sha,
                    "control_preimage_sha256": expected_control_sha256,
                    "artifacts": hashes_published, "effect": "APPLIED",
                    "admitted_worker": False, "service_started": False}
    except FinitePublicationRefused as exc:
        if effect_possible:
            raise FinitePublicationEffectUnknown("original finite publication effect unconfirmed") from exc
        raise
    except FinitePublicationEffectUnknown:
        raise
    except Exception as exc:
        if effect_possible:
            raise FinitePublicationEffectUnknown("original finite publication effect unconfirmed") from exc
        raise FinitePublicationRefused("original Control/Capacity qualification refused") from exc
    finally:
        if lock_fd >= 0:
            try:
                os.close(lock_fd)
            except OSError:
                pass


def publish_disarmed_definition(expected_release_sha: str, expected_control_sha256: str,
                                artifacts: dict[str, bytes], *,
                                verified_capacity_binding) -> dict[str, object]:
    """Retain the legacy root/Capacity-gated entry; native data cannot enter it."""
    _require_publication_inputs(expected_release_sha, expected_control_sha256)
    if not callable(verified_capacity_binding):
        raise FinitePublicationRefused("incumbent Capacity owner is required")
    if type(artifacts) is not dict:
        raise FinitePublicationRefused("exact source bundle required")
    sealed = dict(artifacts)
    verify_candidate(sealed)
    import json
    physical, = _bindings(sealed["bindings.json"])
    worker = json.loads(sealed["worker.json"])
    if "native_capacity_enrollment" in worker:
        raise FinitePublicationRefused("native definition requires its initial owner path")
    try:
        join = CapacityJoin(physical.host_ref, worker["capacity_capability_id"],
                            PROVIDER_CAPACITY_SCHEMA, physical.worker_source_config_digest)
    except CapacityJoinError as exc:
        raise FinitePublicationRefused("Capacity identity is not admissible") from exc

    def prepare(prior, lock_fd, custody):
        if verified_capacity_binding(join) is not True:
            raise FinitePublicationRefused("incumbent Capacity/config binding differs")
        if render_owner_definition(prior, expected_release_sha, join) != sealed:
            raise FinitePublicationRefused("source-rendered finite definition differs")
        def recheck(current):
            if verified_capacity_binding(join) is not True:
                raise FinitePublicationEffectUnknown("original config/Capacity postimage changed")
        return sealed, recheck

    return _publish_selected_definition(expected_release_sha, expected_control_sha256, prepare)


def _require_native_installed_owner(expected_release_sha):
    import sys
    from ops.executive_os.finite_service_lifecycle import SYSTEM
    if (sys.platform != "darwin" or not sys.flags.isolated or not sys.dont_write_bytecode
            or Path(__file__).absolute() != SYSTEM / "releases" / expected_release_sha /
                "ops/executive_os/finite_definition_publication.py"):
        raise FinitePublicationRefused("installed isolated native publication owner required")


def _require_initial_native_context(prior, custody):
    import grp
    import pwd
    from control_plane.codex_provider_realm import _native_open
    from control_plane.executive_physical_resources import load_physical_resource_policy
    from ops.executive_os.finite_reference_assignment import require_initial_reference_context
    from ops.executive_os.subscription_provider_credential import _assert_worker_quiescent
    from ops.executive_os.finite_enrollment_completion import _absent
    from ops.executive_os.finite_service_lifecycle import LABEL, SOCKET, checked_command, parse_override
    require_initial_reference_context(dict(prior.control), dict(prior.worker),
                                      load_physical_resource_policy())
    # No process is weaker than no activation route. Reuse the completion
    # owner's observe-only finite lifecycle checks; never unload or clean up.
    if (owner.ProductionCeoSubmitHost()._loaded_observe_only(LABEL)
            or parse_override(checked_command([
                "/bin/launchctl", "print-disabled", "system"]).stdout.decode())
                not in {"default", "disabled"}):
        raise FinitePublicationRefused("finite service must remain absent and disabled")
    _absent(Path(SOCKET))
    home = Path("/private/var/db/mastermind-executive/workers/minimax-finite-01/provider-home")
    user = pwd.getpwnam("_mastermind_minimax")
    group = grp.getgrnam("_mastermind_minimax")
    if (user.pw_uid, user.pw_gid, group.gr_gid, user.pw_dir, user.pw_shell) != (
            470, 470, 470, str(home), "/usr/bin/false"):
        raise FinitePublicationRefused("native principal identity unavailable")
    _assert_worker_quiescent(470)
    _, info = custody.enter_context(_native_open(home, directory=True, private_uid=470))
    if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (470, 470, 0o700):
        raise FinitePublicationRefused("native private HOME unavailable")


def _read_initial_native_source(select_accepted_native_source):
    """Observe selection; this never creates acceptance, materializes or exports."""
    from control_plane.codex_provider_realm import _native_open, _native_read_config
    from ops.executive_os import capacity_host_artifacts as source_owner
    from ops.executive_os.capacity_source_contract import SYSTEM_ROOT, validate_native_registration_source
    source = validate_native_registration_source(select_accepted_native_source())
    source_root = SYSTEM_ROOT / "capacity-sources/macro" / source["release_commit"]
    with _native_open(source_root, directory=True) as (_, info):
        if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (0, 0, 0o555):
            raise FinitePublicationRefused("native source root custody unavailable")
        manifest, _ = source_owner._verify_installed_repair_source(source_root, source["release_commit"])
        if manifest["schema_version"] != "mastermind.capacity_source_transport/native_v1":
            raise FinitePublicationRefused("native complete source profile required")
    export_path = SYSTEM_ROOT / "config/capacity-source-components-native-v2" / (source["release_commit"] + ".json")
    document = _native_read_config(export_path, source["export_sha256"])
    if (type(document) is not dict
            or set(document) != {"repository_commit", "previous_repository_commit", "material_source_digest", "registrations"}
            or document["repository_commit"] != source["release_commit"]
            or document["previous_repository_commit"] != source["previous_release_commit"]
            or document["material_source_digest"] != source["material_source_digest"]
            or type(document["registrations"]) is not list):
        raise FinitePublicationRefused("accepted native source export differs")
    candidates = [row for row in document["registrations"] if type(row) is dict and
        (row.get("provider"), row.get("billing_mode"), row.get("credential_kind"),
         row.get("execution_surface"), row.get("registration_state")) ==
        ("minimax", "subscription", "api_key", "native_cli", "registered")]
    if len(candidates) != 1:
        raise FinitePublicationRefused("one accepted finite MiniMax registration required")
    return source, document, candidates[0]["capacity_capability_id"]


def _native_candidate_join(artifacts, document):
    import json
    from control_plane import native_capacity_v2 as v2
    from ops.executive_os.capacity_source_contract import validate_native_registration_document
    verify_candidate(artifacts)
    worker = json.loads(artifacts["worker.json"])
    row = validate_native_registration_document(worker, document)
    physical, = _bindings(artifacts["bindings.json"])
    return v2.validate_join({"schema": v2.JOIN_SCHEMA, "provider_capacity_schema": v2.SCHEMA,
        "host_ref": physical.host_ref, "capacity_capability_id": row["capacity_capability_id"],
        "capability_generation": row["capability_generation"],
        "worker_source_config_digest": physical.worker_source_config_digest})


def publish_initial_native_from_installed_sources(expected_release_sha: str,
        expected_control_sha256: str, *, select_accepted_native_source) -> dict[str, object]:
    """Initial, unenrolled publication through the incumbent root/Capacity owners.

    Installed trusted owner code supplies the read-only, no-argument selector.
    No request, plugin, model or config selects that callable or its four pins.
    Its current/predecessor acceptance is separate from complete Git integrity;
    absent acceptance or export must refuse. There is no legacy migration,
    provider observation, enrollment grant, Runtime admission or service effect.
    """
    _require_publication_inputs(expected_release_sha, expected_control_sha256)
    if not callable(select_accepted_native_source):
        raise FinitePublicationRefused("accepted native Capacity source owner required")
    _require_native_installed_owner(expected_release_sha)

    def prepare(prior, lock_fd, custody):
        from ops.executive_os.finite_reference_assignment import prepare_finite_reference_stanza
        _require_definition_absent(lock_fd, DESTINATION.name)
        _require_initial_native_context(prior, custody)
        selected = _read_initial_native_source(select_accepted_native_source)
        source, document, capability = selected
        # Exactly one initial generation, after first-publication qualification.
        stanza = prepare_finite_reference_stanza(registration_source=source,
                                                 realm_generation=1)
        def render(current):
            return _render_owner_definition(current, expected_release_sha,
                host_ref=stanza["host_ref"], capacity_capability_id=capability,
                native_capacity_enrollment=stanza)
        sealed = render(prior)
        joined = _native_candidate_join(sealed, document)
        def recheck(current):
            _require_initial_native_context(current, custody)
            if _read_initial_native_source(select_accepted_native_source) != selected:
                raise FinitePublicationRefused("accepted native source selection changed")
            reproduced = render(current)
            if reproduced != sealed or _native_candidate_join(reproduced, document) != joined:
                raise FinitePublicationRefused("source-rendered native definition differs")
        # Reproduction uses the retained stanza, never a second reference mint.
        recheck(prior)
        return sealed, recheck

    return _publish_selected_definition(expected_release_sha, expected_control_sha256, prepare)


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
