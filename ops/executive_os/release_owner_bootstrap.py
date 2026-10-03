"""Root-only first bootstrap publisher for the existing Executive release owner.

The publisher consumes one already-compiled *disabled* resident PublicationPlan
and creates only the three fixed resident inputs plus the private owner seal
key.  It does not derive authority, enable registration, stage a release,
start a worker, or execute a transition.  Initial bootstrap deliberately
accepts v1 installed evidence only: current v2 physical evidence requires an
existing resident preimage and remains a later migration/qualification step.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass
import errno
import hashlib
import os
from pathlib import Path
import stat
import sys
from typing import Any

from control_plane.executive_release_contract import ReleaseContractError, parse_release_json
from ops.executive_os.release_owner_publication_plan import (
    PublicationFile,
    PublicationPayload,
    PublicationPlan,
)
from ops.executive_os.release_owner_resident_inputs import (
    ReleaseOwnerInputError,
    canonical_file_bytes,
    compile_empty_registry,
    compile_registration,
)

_CANONICAL_CONFIG_ROOT = "/Library/Application Support/MastermindExecutive/config"
_CONFIG_ROOT: Path | str = Path(_CANONICAL_CONFIG_ROOT)
_KEY_PATH: Path | str = Path(_CANONICAL_CONFIG_ROOT) / "release-owner-seal.key"
_ROOT_UID = 0
_WHEEL_GID = 0
_FILE_MODE = 0o400
_KEY_BYTES = 32
_TEMP_PREFIX = ".release-owner-bootstrap."
_REGISTRATION_NAME = "release-owner-registration.json"
_REGISTRY_NAME = "release-owner-staged-transitions.json"
_EVIDENCE_NAME = "release-owner-installed-evidence.json"
_KEY_NAME = "release-owner-seal.key"
_RESIDENT_NAMES = (_REGISTRATION_NAME, _REGISTRY_NAME, _EVIDENCE_NAME)
_CANONICAL_RESIDENT_PATHS = tuple(
    f"{_CANONICAL_CONFIG_ROOT}/{name}" for name in _RESIDENT_NAMES
)
_REQUIRED_PREDICATES = (
    "resident_destinations_absent_or_exact_preimage",
    "resident_parent_direct_root_owned_nonwritable_directory",
    "temporary_files_root_wheel_single_link_same_filesystem",
    "temporary_files_fsync_before_mode_0400",
    "atomic_rename_each_file_then_fsync_parent",
    "readback_path_length_sha256_mode_uid_gid_exact",
    "registration_remains_disabled",
    "release_commit_remains_permanently_disarmed",
)
_DISARMED = {
    "commit_prepared_release_transition": False,
    "installer_arming": False,
    "worker_start": False,
}
_EVIDENCE_V1_FIELDS = frozenset({
    "schema", "owner_installation_id", "target_ref", "registration_generation",
    "release_commit", "release_tree", "control_config_digest", "broker_config_digest",
    "installed_configuration_digest", "python_runtime_provenance_digest",
    "provider_binary_attestation_digest", "provider_attestation_role",
    "provider_attestation_boot_id", "issuer_binding_digest",
    "issuer_binding_owner_installation_id", "issuer_binding_role",
    "issuer_binding_release_commit", "issuer_binding_boot_id",
    "issuer_binding_observed_at", "provider_attestation_observed_at",
    "production_disarming",
})


class BootstrapError(RuntimeError):
    """Closed bootstrap refusal code; rejected data and secrets are never echoed."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _refuse(code: str) -> BootstrapError:
    return BootstrapError(code)


@dataclass(frozen=True)
class BootstrapReceipt:
    schema: str
    action: str
    owner_installation_id: str
    target_ref: str
    release_commit: str
    manifest_sha256: str


def _canonical_document(raw: object, code: str) -> dict[str, Any]:
    if type(raw) is not bytes or not raw.endswith(b"\n") or b"\n" in raw[:-1]:
        raise _refuse(code)
    try:
        value = parse_release_json(raw[:-1]).to_dict()
        if canonical_file_bytes(value) != raw:
            raise ValueError("noncanonical")
    except (ReleaseContractError, ReleaseOwnerInputError, UnicodeError, ValueError, TypeError):
        raise _refuse(code) from None
    return value


def _validate_plan(plan: PublicationPlan) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, bytes]]:
    """Validate the inert bootstrap envelope without authenticating its evidence."""
    if type(plan) is not PublicationPlan:
        raise _refuse("BOOTSTRAP_PLAN_INVALID")
    if (
        plan.kind != "resident"
        or plan.directory != _CANONICAL_CONFIG_ROOT
        or plan.directory_mode is not None
        or plan.predicates != _REQUIRED_PREDICATES
        or len(plan.files) != 3
        or len(plan.payloads) != 3
    ):
        raise _refuse("BOOTSTRAP_PLAN_INVALID")
    if hashlib.sha256(plan.manifest_bytes).hexdigest() != plan.manifest_sha256:
        raise _refuse("BOOTSTRAP_PLAN_INVALID")

    manifest = _canonical_document(plan.manifest_bytes, "BOOTSTRAP_PLAN_INVALID")
    expected_manifest_keys = {
        "schema", "kind", "directory", "directory_uid", "directory_gid",
        "files", "predicates", "context", "evidence_authentication",
        "production_disarming",
    }
    if (
        set(manifest) != expected_manifest_keys
        or manifest["schema"] != "mastermind.executive_release_owner_publication_plan/v1"
        or manifest["kind"] != "resident"
        or manifest["directory"] != _CANONICAL_CONFIG_ROOT
        or manifest["directory_uid"] != 0
        or manifest["directory_gid"] != 0
        or manifest["predicates"] != list(_REQUIRED_PREDICATES)
        or manifest["evidence_authentication"]
        != "UNAUTHENTICATED_UNTIL_INSTALLED_CONSUMER_REDERIVES"
        or manifest["production_disarming"] != _DISARMED
        or type(manifest.get("context")) is not dict
        or manifest["context"].get("resident_preimage") != "ABSENT"
    ):
        raise _refuse("BOOTSTRAP_PLAN_INVALID")

    payloads: dict[str, bytes] = {}
    inventory: list[dict[str, object]] = []
    for index, canonical_path in enumerate(_CANONICAL_RESIDENT_PATHS):
        file = plan.files[index]
        payload = plan.payloads[index]
        if type(file) is not PublicationFile or type(payload) is not PublicationPayload:
            raise _refuse("BOOTSTRAP_PLAN_INVALID")
        if file.path != canonical_path or payload.path != canonical_path:
            raise _refuse("BOOTSTRAP_PLAN_INVALID")
        if (
            type(payload.data) is not bytes
            or file.length != len(payload.data)
            or file.sha256 != hashlib.sha256(payload.data).hexdigest()
            or file.mode != _FILE_MODE
            or file.uid != 0
            or file.gid != 0
        ):
            raise _refuse("BOOTSTRAP_PLAN_INVALID")
        name = Path(canonical_path).name
        payloads[name] = payload.data
        inventory.append({
            "path": file.path,
            "length": file.length,
            "sha256": file.sha256,
            "mode": file.mode,
            "uid": file.uid,
            "gid": file.gid,
        })
    if manifest["files"] != inventory or set(payloads) != set(_RESIDENT_NAMES):
        raise _refuse("BOOTSTRAP_PLAN_INVALID")

    registration = _canonical_document(payloads[_REGISTRATION_NAME], "BOOTSTRAP_PLAN_INVALID")
    try:
        if compile_registration(
            owner_installation_id=registration["owner_installation_id"],
            target_ref=registration["target_ref"],
            key_id=registration["key_id"],
            trust_generation=registration["trust_generation"],
            app_generation=registration["app_generation"],
            registration_generation=registration["registration_generation"],
            enabled=registration["enabled"],
        ) != payloads[_REGISTRATION_NAME]:
            raise ValueError("registration mismatch")
    except (KeyError, ReleaseOwnerInputError, ValueError, TypeError):
        raise _refuse("BOOTSTRAP_PLAN_INVALID") from None
    if registration["enabled"] is not False:
        raise _refuse("BOOTSTRAP_PLAN_ARMED")

    registry = _canonical_document(payloads[_REGISTRY_NAME], "BOOTSTRAP_PLAN_INVALID")
    try:
        if (
            registry.get("transitions") != []
            or compile_empty_registry(
                registration_generation=registry["registration_generation"],
                registry_generation=registry["registry_generation"],
            ) != payloads[_REGISTRY_NAME]
        ):
            raise ValueError("registry mismatch")
    except (KeyError, ReleaseOwnerInputError, ValueError, TypeError):
        raise _refuse("BOOTSTRAP_PLAN_INVALID") from None
    if registry["registration_generation"] != registration["registration_generation"]:
        raise _refuse("BOOTSTRAP_PLAN_INVALID")

    evidence = _canonical_document(payloads[_EVIDENCE_NAME], "BOOTSTRAP_PLAN_INVALID")
    # Physical evidence v2 is deliberately not admissible from ABSENT state.
    if evidence.get("schema") != "mastermind.executive_release_owner_installed_evidence/v1":
        raise _refuse("BOOTSTRAP_EVIDENCE_VERSION")
    if set(evidence) != _EVIDENCE_V1_FIELDS:
        raise _refuse("BOOTSTRAP_PLAN_INVALID")
    if evidence.get("production_disarming") != {
        "schema": "mastermind.executive_release_disarming/v1", **_DISARMED
    }:
        raise _refuse("BOOTSTRAP_PLAN_ARMED")
    if (
        evidence.get("owner_installation_id") != registration["owner_installation_id"]
        or evidence.get("target_ref") != registration["target_ref"]
        or evidence.get("registration_generation") != registration["registration_generation"]
        or evidence.get("issuer_binding_owner_installation_id") != registration["owner_installation_id"]
        or evidence.get("issuer_binding_release_commit") != evidence.get("release_commit")
        or evidence.get("issuer_binding_role") != "control"
        or evidence.get("provider_attestation_role") != "codex_worker"
    ):
        raise _refuse("BOOTSTRAP_PLAN_INVALID")
    context = manifest["context"]
    for key, observed in (
        ("owner_installation_id", registration["owner_installation_id"]),
        ("target_ref", registration["target_ref"]),
        ("release_commit", evidence.get("release_commit")),
        ("release_tree", evidence.get("release_tree")),
    ):
        if context.get(key) != observed:
            raise _refuse("BOOTSTRAP_PLAN_INVALID")
    return registration, registry, evidence, payloads


def _open_config_root() -> tuple[int, os.stat_result]:
    path = Path(_CONFIG_ROOT)
    descriptor: int | None = None
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
            raise _refuse("BOOTSTRAP_ROOT_UNSAFE")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        current = os.fstat(descriptor)
    except BootstrapError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except OSError:
        if descriptor is not None:
            os.close(descriptor)
        raise _refuse("BOOTSTRAP_ROOT_UNSAFE") from None
    if (
        (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino)
        or current.st_uid != _ROOT_UID
        or current.st_gid != _WHEEL_GID
        or stat.S_IMODE(current.st_mode) & 0o022
        or not stat.S_ISDIR(current.st_mode)
    ):
        os.close(descriptor)
        raise _refuse("BOOTSTRAP_ROOT_UNSAFE")
    return descriptor, current


def _entry_exists(directory_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError:
        raise _refuse("BOOTSTRAP_ROOT_UNSAFE") from None
    return True


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("short write")
        view = view[written:]


def _make_temp(directory_fd: int, directory: os.stat_result, name: str, data: bytes) -> str:
    suffix = os.urandom(12).hex()
    temporary = f"{_TEMP_PREFIX}{os.getpid()}.{suffix}.{name}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
    complete = False
    try:
        _write_all(fd, data)
        inherited = os.fstat(fd)
        if (inherited.st_uid, inherited.st_gid) != (_ROOT_UID, _WHEEL_GID):
            os.fchown(fd, _ROOT_UID, _WHEEL_GID)
        os.fchmod(fd, _FILE_MODE)
        os.fsync(fd)
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_dev != directory.st_dev
            or info.st_nlink != 1
            or info.st_uid != _ROOT_UID
            or info.st_gid != _WHEEL_GID
            or stat.S_IMODE(info.st_mode) != _FILE_MODE
            or info.st_size != len(data)
        ):
            raise OSError("temporary postimage mismatch")
        complete = True
    finally:
        os.close(fd)
        if not complete:
            try:
                os.unlink(temporary, dir_fd=directory_fd)
                os.fsync(directory_fd)
            except FileNotFoundError:
                pass
            except OSError as error:
                raise BootstrapError("BOOTSTRAP_EFFECT_UNKNOWN") from error
    return temporary


def _rename_no_replace(directory_fd: int, source: str, destination: str) -> None:
    """Atomically publish one temp name without ever replacing a destination."""
    libc = ctypes.CDLL(None, use_errno=True)
    source_b = os.fsencode(source)
    destination_b = os.fsencode(destination)
    if sys.platform == "darwin" and hasattr(libc, "renameatx_np"):
        function = libc.renameatx_np
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        rc = function(directory_fd, source_b, directory_fd, destination_b, 0x00000004)  # RENAME_EXCL
    elif sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
        function = libc.renameat2
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        rc = function(directory_fd, source_b, directory_fd, destination_b, 0x00000001)  # RENAME_NOREPLACE
    else:
        # Safe fallback for test/unsupported hosts: same-filesystem hard link is
        # no-clobber; unlinking the temp leaves exactly one final link.
        os.link(source, destination, src_dir_fd=directory_fd, dst_dir_fd=directory_fd, follow_symlinks=False)
        os.unlink(source, dir_fd=directory_fd)
        return
    if rc != 0:
        error = ctypes.get_errno()
        if error == errno.EEXIST:
            raise FileExistsError(error, os.strerror(error), destination)
        raise OSError(error, os.strerror(error), destination)


def _readback(directory_fd: int, directory: os.stat_result, name: str, expected: bytes) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(name, flags, dir_fd=directory_fd)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_dev != directory.st_dev
            or info.st_nlink != 1
            or info.st_uid != _ROOT_UID
            or info.st_gid != _WHEEL_GID
            or stat.S_IMODE(info.st_mode) != _FILE_MODE
            or info.st_size != len(expected)
        ):
            raise OSError("published metadata mismatch")
        chunks = bytearray()
        while len(chunks) < len(expected) + 1:
            block = os.read(fd, min(65536, len(expected) + 1 - len(chunks)))
            if not block:
                break
            chunks.extend(block)
        if bytes(chunks) != expected:
            raise OSError("published bytes mismatch")
    finally:
        os.close(fd)


def _cleanup(directory_fd: int, finals: list[str], temporaries: list[str]) -> bool:
    clean = True
    for name in reversed(finals):
        try:
            os.unlink(name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        except OSError:
            clean = False
    for name in temporaries:
        try:
            os.unlink(name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        except OSError:
            clean = False
    try:
        os.fsync(directory_fd)
    except OSError:
        clean = False
    return clean


def publish_initial_resident_plan(plan: PublicationPlan) -> BootstrapReceipt:
    """Publish one first disabled resident set, or fail without replacing state."""
    # Root is checked before observing the caller's plan by design.
    if os.geteuid() != _ROOT_UID:
        raise _refuse("BOOTSTRAP_ROOT_REQUIRED")
    registration, _registry, evidence, payloads = _validate_plan(plan)
    directory_fd, directory = _open_config_root()
    temporaries: list[str] = []
    finals: list[str] = []
    try:
        key_name = Path(_KEY_PATH).name
        names = [*_RESIDENT_NAMES, key_name]
        if key_name != _KEY_NAME or len(set(names)) != 4:
            raise _refuse("BOOTSTRAP_PLAN_INVALID")
        # An orphaned bootstrap temp proves an interrupted prior publish.
        # Preserve that effect state before applying the ordinary occupied
        # destination refusal used for completed/foreign preimages.
        try:
            entries = os.listdir(directory_fd)
        except (TypeError, OSError):
            entries = os.listdir(Path(_CONFIG_ROOT))
        if any(name.startswith(_TEMP_PREFIX) for name in entries):
            raise _refuse("BOOTSTRAP_EFFECT_UNKNOWN")
        for name in names:
            if _entry_exists(directory_fd, name):
                raise _refuse("BOOTSTRAP_DESTINATION_OCCUPIED")

        key = os.urandom(_KEY_BYTES)
        if len(key) != _KEY_BYTES or len(set(key)) <= 1:
            raise _refuse("BOOTSTRAP_RANDOM_UNAVAILABLE")
        material = [(name, payloads[name]) for name in _RESIDENT_NAMES]
        material.append((key_name, key))
        for name, data in material:
            temporaries.append(_make_temp(directory_fd, directory, name, data))

        for (name, _data), temporary in zip(material, tuple(temporaries), strict=True):
            try:
                _rename_no_replace(directory_fd, temporary, name)
            except FileExistsError:
                if not _cleanup(directory_fd, finals, temporaries):
                    raise _refuse("BOOTSTRAP_EFFECT_UNKNOWN") from None
                raise _refuse("BOOTSTRAP_DESTINATION_OCCUPIED") from None
            finals.append(name)
            temporaries.remove(temporary)
        os.fsync(directory_fd)
        for name, data in material:
            _readback(directory_fd, directory, name, data)
        os.fsync(directory_fd)
    except BootstrapError:
        raise
    except Exception:
        if not _cleanup(directory_fd, finals, temporaries):
            raise _refuse("BOOTSTRAP_EFFECT_UNKNOWN") from None
        raise _refuse("BOOTSTRAP_PUBLISH_FAILED") from None
    finally:
        os.close(directory_fd)

    return BootstrapReceipt(
        schema="mastermind.executive_release_owner_bootstrap_receipt/v1",
        action="BOOTSTRAPPED_DISARMED",
        owner_installation_id=registration["owner_installation_id"],
        target_ref=registration["target_ref"],
        release_commit=evidence["release_commit"],
        manifest_sha256=plan.manifest_sha256,
    )


__all__ = (
    "BootstrapError",
    "BootstrapReceipt",
    "publish_initial_resident_plan",
)
