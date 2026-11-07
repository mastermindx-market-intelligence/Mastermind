"""Bounded role metadata for the existing Hermes harness owner.

One read facade over an explicitly supplied role state directory. It projects
what the incumbent installer already wrote -- the install manifest, the current
release receipt and the role profile -- into a closed observation record.

The ``role_metadata`` projection is secret-free: it never reads a credential,
calls a provider, observes a running service, selects a model generation, or
attests a host/source binding. ``doctor`` and the secret loader are not readers
here and are never imported by this module.

This module also hosts the shared catalog projections ``model_choices`` and
``model_selection``, which the existing ``hermesctl`` commands publish. Those
two are the incumbent CLI's own views and keep the credential *names* that
``hermesctl models`` and ``hermesctl status`` already published; they are not
part of the role metadata projection and must not be offered to a panel.

The state path is supplied only by trusted installation composition. There is
no home scan, no environment-selected fallback, no repository-profile fallback
and no host guess. A caller without a trusted host binding has no observation
at all: a missing binding is *not* ``ABSENT``, because no state on one host
can prove that another host's role is absent. The caller owns that binding and
reports it separately; this facade records ``source_binding: NOT_ATTESTED``.

``ABSENT`` is reserved for one case: the explicitly selected role
installation root is readable and qualified, the incumbent manifest is
actually absent there, and the root carries no surviving incumbent install
evidence. Every other failure -- missing root, unreadable or malformed
metadata, oversized file, role or service swap, inconsistent current link, a
manifest that vanished from an otherwise installed root, path escape, or a
change observed during the read -- is ``UNAVAILABLE`` with one bounded fixed
reason code.

Module-level imports stay stdlib-only. The Mastermind catalog and profile
owners are imported inside the functions that use them, so importing this
module pulls in no provider client, no secret loader and no runtime package.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat


ROLE_METADATA_SCHEMA = "mastermind.hermes.role_metadata.v1"

# The two Hermes runtime profile roles. These are the runtime's own role and
# service identity; a caller-facing role id is mapped through the existing
# role catalog with ``profile_for_role_id``.
QUALIFIED_ROLES = ("mmmeta", "mmsecretary")

ABSENT = "ABSENT"
CONFIGURATION_OBSERVED = "CONFIGURATION_OBSERVED"
UNAVAILABLE = "UNAVAILABLE"

# One bounded, enumerable reason vocabulary. Every code below is a fixed
# literal: no path, message, exception text or credential material is ever
# carried in the projection.
REASON_CODES = frozenset({
    "CONFIGURATION_CONSISTENT",
    "INSTALL_MANIFEST_ABSENT",
    "ROLE_UNQUALIFIED",
    "STATE_ROOT_MISSING",
    "STATE_ROOT_NOT_DIRECTORY",
    "STATE_ROOT_NOT_QUALIFIED",
    "STATE_ROOT_SYMLINK_REFUSED",
    "STATE_ROOT_UNREADABLE",
    "METADATA_NOT_REGULAR_FILE",
    "METADATA_TOO_LARGE",
    "METADATA_UNREADABLE",
    "MANIFEST_MISSING",
    "MANIFEST_MALFORMED",
    "MANIFEST_INCONSISTENT",
    "MANIFEST_ROLE_MISMATCH",
    "CURRENT_LINK_INVALID",
    "CURRENT_LINK_UNREADABLE",
    "RELEASE_MISMATCH",
    "RELEASE_UNAVAILABLE",
    "RECEIPT_MISSING",
    "RECEIPT_MALFORMED",
    "RECEIPT_INCONSISTENT",
    "PROFILE_MISSING",
    "PROFILE_UNQUALIFIED",
    "PROFILE_ROLE_MISMATCH",
    "PROFILE_DIGEST_MISMATCH",
    "CONFIG_MISSING",
    "CONFIG_PATH_INVALID",
    "CONFIG_DIGEST_MISMATCH",
    "OBSERVATION_CHANGED",
    "REQUESTED_CONFIGURATION_UNQUALIFIED",
    "INTERNAL_READ_FAILURE",
})

_MAX_METADATA_BYTES = 64 * 1024
_SHA = re.compile(r"^[0-9a-f]{40}$")
# The incumbent installer writes the current release as a relative symlink
# ``releases/<id>``. An absolute target, a nested path or any traversal is
# refused rather than followed.
_CURRENT_TARGET = re.compile(r"^releases/([0-9]{1,12})$")

__all__ = [
    "ABSENT",
    "CONFIGURATION_OBSERVED",
    "QUALIFIED_ROLES",
    "REASON_CODES",
    "ROLE_METADATA_SCHEMA",
    "UNAVAILABLE",
    "model_choices",
    "model_selection",
    "profile_for_role_id",
    "role_metadata",
]


class _Unavailable(Exception):
    """A typed refusal carrying one fixed reason code and nothing else."""

    __slots__ = ("code",)

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def role_metadata(state_dir: Path, expected_role: str) -> dict:
    """Project one role's installed configuration. Never raises for a bad state.

    ``state_dir`` must be the role's own installation state directory, supplied
    by trusted installation composition. ``expected_role`` must be one of
    :data:`QUALIFIED_ROLES`. The result is always the same closed projection.

    ``INTERNAL_READ_FAILURE`` means this reader failed unexpectedly; it is not
    a statement about the installation. Every other reason describes the
    observed state.
    """
    if expected_role not in QUALIFIED_ROLES:
        return _projection(role="", state=UNAVAILABLE, reason="ROLE_UNQUALIFIED")
    try:
        root = Path(state_dir)
    except TypeError:
        return _projection(role=expected_role, state=UNAVAILABLE, reason="STATE_ROOT_NOT_QUALIFIED")
    try:
        with _HeldObservation(root) as held:
            if not held.present(held.root_fd, "install-manifest.json"):
                evidence = held.install_evidence()
                # The final absence check follows all evidence inspection.
                held.finish()
                return _projection(
                    role=expected_role,
                    state=UNAVAILABLE if evidence else ABSENT,
                    reason="MANIFEST_MISSING" if evidence else "INSTALL_MANIFEST_ABSENT",
                )
            observation = _observe(held, expected_role)
            held.finish()
    except _Unavailable as exc:
        return _projection(role=expected_role, state=UNAVAILABLE, reason=exc.code)
    except Exception:
        # A read facade is fail-closed: an unexpected internal failure is a
        # typed unavailable observation, never an exception into the caller.
        return _projection(role=expected_role, state=UNAVAILABLE, reason="INTERNAL_READ_FAILURE")
    return _projection(
        role=expected_role,
        state=CONFIGURATION_OBSERVED,
        reason="CONFIGURATION_CONSISTENT",
        requested=observation["requested"],
        provenance=observation["provenance"],
    )


def profile_for_role_id(role_id: str) -> str:
    """Map one caller-facing role id to its Hermes profile name.

    The existing role catalog owns the mapping. No second catalog is created
    here, and an unmapped id is refused rather than guessed.
    """
    from integrations.hermes_models.contract import ROLES

    for spec in ROLES.values():
        if spec.role == role_id and spec.profile in QUALIFIED_ROLES:
            return spec.profile
    raise KeyError("unknown hermes role id")


def model_choices(role: str) -> dict:
    """Source-configurable BYOK choices for one role. Selection is not admission.

    Shared with the existing ``hermesctl models`` command so the CLI and the
    role metadata facade read one catalog projection.
    """
    from integrations.hermes_models.contract import PROFILE_PRIMARY, native_provider_choices

    return {
        "role": role,
        "default_provider_id": PROFILE_PRIMARY[role],
        "choices": [{
            "provider_id": spec.provider_id,
            "native_provider": spec.hermes_name,
            "requested_model": spec.served_model,
            "credential_file_env": spec.credential_file_env,
        } for spec in native_provider_choices(role)],
        "selection_is_admission": False,
        "automatic_fallback": False,
        "provider_called": False,
        "credentials_read": False,
    }


def model_selection(profile) -> dict:
    """The observed native selection for one loaded profile.

    Shared with the existing CLI status projection. This is the CLI-shaped
    view, which keeps the incumbent credential *names*; the role metadata
    facade uses its own narrower projection that omits them.
    """
    from integrations.hermes_models.contract import native_provider
    from integrations.hermes_runtime.errors import RuntimeRefusal

    try:
        spec = native_provider(profile.role, profile.native_provider_id)
    except (ValueError, KeyError):
        raise RuntimeRefusal("NATIVE_MODEL_SELECTION_UNQUALIFIED") from None
    return {
        "provider_id": spec.provider_id,
        "native_provider": spec.hermes_name,
        "requested_model": spec.served_model,
        "served_model_verified": False,
        "credential_env": spec.credential_env,
        "credential_file_env": spec.credential_file_env,
        "automatic_fallback": False,
        "provider_called": False,
    }


def _projection(
    *,
    role: str,
    state: str,
    reason: str,
    requested: dict | None = None,
    provenance: dict | None = None,
) -> dict:
    payload: dict = {
        "schema": ROLE_METADATA_SCHEMA,
        "role": role,
        "state": state,
        "reason": reason,
        # This facade never attests a host or source binding. The caller owns
        # that binding and keeps source-unbound distinct from ABSENT.
        "source_binding": "NOT_ATTESTED",
        "proof": {
            "credentials_read": False,
            "provider_called": False,
            "service_observed": False,
            "served_model_verified": False,
            "credential_enrollment": "UNVERIFIED",
        },
    }
    if requested is not None:
        payload["requested"] = requested
    if provenance is not None:
        payload["provenance"] = provenance
    return payload


def _observe(held: _HeldObservation, role: str) -> dict:
    """Read one installed role's metadata and project it. Raises ``_Unavailable``."""
    from integrations.hermes_models.contract import native_provider
    from integrations.hermes_runtime.profile import load_profile_bytes

    root = held.root
    manifest_bytes = held.read(held.root_fd, "install-manifest.json", missing="MANIFEST_MISSING")
    manifest = _loads_object(manifest_bytes, malformed="MANIFEST_MALFORMED")
    _assert_manifest(manifest, root, role)

    release_id, release_fd = held.current_release()
    release_dir = root / "releases" / release_id
    if manifest.get("current_release") != release_id:
        raise _Unavailable("RELEASE_MISMATCH")

    receipt_bytes = held.read(release_fd, "install-receipt.json", missing="RECEIPT_MISSING")
    receipt = _loads_object(receipt_bytes, malformed="RECEIPT_MALFORMED")
    _assert_receipt(receipt, role, manifest.get("sha"))

    profile_bytes = held.read(release_fd, "profile.yaml", missing="PROFILE_MISSING")
    profile_digest = _sha256(profile_bytes)
    if receipt.get("profile_sha256") != profile_digest:
        raise _Unavailable("PROFILE_DIGEST_MISMATCH")
    try:
        profile = load_profile_bytes(profile_bytes, source_path=release_dir / "profile.yaml")
    except (RuntimeError, OSError, ValueError):
        # The profile owner refuses with its own codes; the facade keeps one
        # fixed reason and never forwards the underlying text.
        raise _Unavailable("PROFILE_UNQUALIFIED") from None
    if not _same_state_root(profile.state_dir, root):
        raise _Unavailable("PROFILE_UNQUALIFIED")
    if profile.role != role or profile.service_name != f"hermes-runtime-{role}":
        raise _Unavailable("PROFILE_ROLE_MISMATCH")
    if profile.sha != manifest.get("sha"):
        raise _Unavailable("MANIFEST_INCONSISTENT")

    config_fd = release_fd
    for part in ("hermes-home", "profiles", role):
        config_fd = held.directory(config_fd, part, missing="CONFIG_MISSING", invalid="CONFIG_PATH_INVALID")
    config_bytes = held.read(config_fd, "config.yaml", missing="CONFIG_MISSING")
    config_digest = _sha256(config_bytes)
    if receipt.get("hermes_config_sha256") != config_digest:
        raise _Unavailable("CONFIG_DIGEST_MISMATCH")

    try:
        spec = native_provider(role, profile.native_provider_id)
    except (ValueError, KeyError):
        raise _Unavailable("REQUESTED_CONFIGURATION_UNQUALIFIED") from None

    digests = {
        "manifest": _sha256(manifest_bytes),
        "receipt": _sha256(receipt_bytes),
        "profile": profile_digest,
        "config": config_digest,
    }
    return {
        "requested": {
            "provider_id": spec.provider_id,
            "native_provider": spec.hermes_name,
            "requested_model": spec.served_model,
        },
        "provenance": {
            "upstream_sha": manifest["sha"],
            "release": release_id,
            "manifest_sha256": digests["manifest"],
            "profile_sha256": digests["profile"],
            "hermes_config_sha256": digests["config"],
            "upstream_attested": receipt["upstream_attested"],
        },
    }


def _assert_manifest(manifest: dict, root: Path, role: str) -> None:
    from integrations.hermes_runtime.constants import MANIFEST_SCHEMA

    if manifest.get("schema") != MANIFEST_SCHEMA or manifest.get("owns_state_dir") is not True:
        raise _Unavailable("MANIFEST_INCONSISTENT")
    if manifest.get("service_name") != f"hermes-runtime-{role}":
        raise _Unavailable("MANIFEST_ROLE_MISMATCH")
    sha = manifest.get("sha")
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise _Unavailable("MANIFEST_INCONSISTENT")
    state_value = manifest.get("state_dir")
    if not isinstance(state_value, str) or not state_value:
        raise _Unavailable("MANIFEST_INCONSISTENT")
    if not _same_state_root(state_value, root):
        raise _Unavailable("MANIFEST_INCONSISTENT")


def _assert_receipt(receipt: dict, role: str, sha: str) -> None:
    from integrations.hermes_runtime.constants import INSTALL_SCHEMA

    if (
        receipt.get("schema") != INSTALL_SCHEMA
        or receipt.get("status") != "RELEASE_WRITTEN"
        or receipt.get("role") != role
        or receipt.get("sha") != sha
        or not isinstance(receipt.get("upstream_attested"), bool)
    ):
        raise _Unavailable("RECEIPT_INCONSISTENT")
    for field in ("profile_sha256", "hermes_config_sha256"):
        value = receipt.get(field)
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise _Unavailable("RECEIPT_INCONSISTENT")


def _directory_identity(info) -> tuple:
    # Directory timestamps are deliberately excluded: unrelated entries in a
    # shared ancestor may change without replacing this descriptor's edge.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)


def _file_identity(info) -> tuple:
    return (*_directory_identity(info), info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _same_state_root(value, root: Path) -> bool:
    if not isinstance(value, (str, Path)) or any(c in str(value) for c in "\x00\n\r\t"):
        return False
    path = Path(value)
    # Compare physical, lexically normalized paths. Do not follow an alias in
    # a document merely to make its declared state directory match the reader.
    return path.anchor == "/" and ".." not in path.parts and path == root


def _dedicated_root(state: Path) -> bool:
    banned = {Path(p) for p in ("/", "/tmp", "/var", "/home", "/etc",
                                  "/private/tmp", "/private/var", "/private/etc")}
    try:
        home = Path.home()
        banned.update({home, home / ".config"})
    except (RuntimeError, OSError):
        pass
    return state not in banned and len(state.parts) >= 3


class _HeldObservation:
    """Hold the fixed metadata leaves and their entire physical directory chain.

    All content reads use descriptors opened relative to held parents. The
    finalizer checks directory edges, file identity and bytes, current-link
    identity, and negative evidence before returning a projection. This is
    detection of observed changes, not an atomic multi-file filesystem view.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root_fd = -1
        self.fds: list[int] = []
        self.directories: list[tuple] = []
        self.files: list[tuple] = []
        self.absent: list[tuple[int, str]] = []
        self.empty: list[tuple] = []
        self.current: tuple | None = None
        self.root_contents: tuple | None = None

    def __enter__(self):
        if (self.root.anchor != "/" or ".." in self.root.parts
                or any(c in str(self.root) for c in "\x00\n\r\t")
                or not _dedicated_root(self.root)):
            raise _Unavailable("STATE_ROOT_NOT_QUALIFIED")
        try:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            fd = os.open("/", flags)
            self.fds.append(fd)
            self.directories.append((fd, None, None, _directory_identity(os.fstat(fd))))
            for part in self.root.parts[1:]:
                fd = self.directory(
                    fd, part, missing="STATE_ROOT_MISSING", invalid="STATE_ROOT_NOT_DIRECTORY",
                    symlink="STATE_ROOT_SYMLINK_REFUSED", unreadable="STATE_ROOT_UNREADABLE",
                )
            self.root_fd = fd
            self.root_contents = _file_identity(os.fstat(fd))
            return self
        except (AttributeError, OSError):
            self.close()
            raise _Unavailable("STATE_ROOT_UNREADABLE") from None
        except BaseException:
            self.close()
            raise

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        while self.fds:
            os.close(self.fds.pop())

    def directory(
        self, parent: int, name: str, *, missing: str, invalid: str,
        symlink: str | None = None, unreadable: str | None = None,
    ) -> int:
        try:
            before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            raise _Unavailable(missing) from None
        except OSError:
            raise _Unavailable(unreadable or invalid) from None
        if stat.S_ISLNK(before.st_mode):
            raise _Unavailable(symlink or invalid)
        if not stat.S_ISDIR(before.st_mode):
            raise _Unavailable(invalid)
        try:
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        except OSError as exc:
            if exc.errno in {errno.ELOOP, errno.EMLINK, errno.ENOTDIR, errno.ENOENT}:
                raise _Unavailable("OBSERVATION_CHANGED") from None
            raise _Unavailable(unreadable or invalid) from None
        self.fds.append(fd)
        after = os.fstat(fd)
        if not stat.S_ISDIR(after.st_mode) or _directory_identity(before) != _directory_identity(after):
            raise _Unavailable("OBSERVATION_CHANGED")
        self.directories.append((fd, parent, name, _directory_identity(after)))
        return fd

    def present(self, parent: int, name: str) -> bool:
        try:
            os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            self.absent.append((parent, name))
            return False
        except OSError:
            raise _Unavailable("METADATA_UNREADABLE") from None
        return True

    def install_evidence(self) -> bool:
        if self.present(self.root_fd, "current"):
            return True
        if not self.present(self.root_fd, "releases"):
            return False
        try:
            fd = self.directory(self.root_fd, "releases", missing="OBSERVATION_CHANGED",
                                invalid="MANIFEST_MISSING")
            before = _file_identity(os.fstat(fd))
            with os.scandir(fd) as entries:
                evidence = next(entries, None) is not None
            if not evidence:
                self.empty.append((fd, before))
            return evidence
        except _Unavailable as exc:
            if exc.code == "OBSERVATION_CHANGED":
                raise
            return True
        except OSError:
            return True

    def current_release(self) -> tuple[str, int]:
        try:
            before = os.stat("current", dir_fd=self.root_fd, follow_symlinks=False)
            if not stat.S_ISLNK(before.st_mode):
                raise _Unavailable("CURRENT_LINK_INVALID")
            target = os.readlink("current", dir_fd=self.root_fd)
            after = os.stat("current", dir_fd=self.root_fd, follow_symlinks=False)
        except FileNotFoundError:
            raise _Unavailable("CURRENT_LINK_INVALID") from None
        except OSError:
            raise _Unavailable("CURRENT_LINK_UNREADABLE") from None
        if _file_identity(before) != _file_identity(after):
            raise _Unavailable("OBSERVATION_CHANGED")
        match = _CURRENT_TARGET.fullmatch(target)
        if match is None:
            raise _Unavailable("CURRENT_LINK_INVALID")
        self.current = (_file_identity(after), target)
        releases = self.directory(self.root_fd, "releases", missing="RELEASE_UNAVAILABLE",
                                  invalid="RELEASE_UNAVAILABLE")
        release_id = match.group(1)
        release = self.directory(releases, release_id, missing="RELEASE_UNAVAILABLE",
                                 invalid="RELEASE_UNAVAILABLE")
        return release_id, release

    def read(self, parent: int, name: str, *, missing: str) -> bytes:
        try:
            before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            raise _Unavailable(missing) from None
        except OSError:
            raise _Unavailable("METADATA_UNREADABLE") from None
        if not stat.S_ISREG(before.st_mode):
            raise _Unavailable("METADATA_NOT_REGULAR_FILE")
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        except FileNotFoundError:
            raise _Unavailable("OBSERVATION_CHANGED") from None
        except OSError as exc:
            if exc.errno in {errno.ELOOP, errno.EMLINK}:
                raise _Unavailable("METADATA_NOT_REGULAR_FILE") from None
            raise _Unavailable("METADATA_UNREADABLE") from None
        self.fds.append(fd)
        after = os.fstat(fd)
        if not stat.S_ISREG(after.st_mode):
            raise _Unavailable("METADATA_NOT_REGULAR_FILE")
        if _file_identity(before) != _file_identity(after):
            raise _Unavailable("OBSERVATION_CHANGED")
        data = _read_fd(fd)
        if _file_identity(after) != _file_identity(os.fstat(fd)):
            raise _Unavailable("OBSERVATION_CHANGED")
        self.files.append((fd, parent, name, _file_identity(after), data))
        return data

    def _check_directories(self) -> None:
        for fd, parent, name, identity in self.directories:
            if _directory_identity(os.fstat(fd)) != identity:
                raise _Unavailable("OBSERVATION_CHANGED")
            if parent is not None and _directory_identity(
                    os.stat(name, dir_fd=parent, follow_symlinks=False)) != identity:
                raise _Unavailable("OBSERVATION_CHANGED")

    def finish(self) -> None:
        try:
            self._check_directories()
            for fd, parent, name, identity, data in self.files:
                if (_file_identity(os.fstat(fd)) != identity
                        or _file_identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != identity):
                    raise _Unavailable("OBSERVATION_CHANGED")
                os.lseek(fd, 0, os.SEEK_SET)
                if _read_fd(fd) != data or _file_identity(os.fstat(fd)) != identity:
                    raise _Unavailable("OBSERVATION_CHANGED")
            if self.current is not None:
                info = os.stat("current", dir_fd=self.root_fd, follow_symlinks=False)
                target = os.readlink("current", dir_fd=self.root_fd)
                if (_file_identity(info), target) != self.current:
                    raise _Unavailable("OBSERVATION_CHANGED")
            for fd, identity in self.empty:
                with os.scandir(fd) as entries:
                    if next(entries, None) is not None:
                        raise _Unavailable("OBSERVATION_CHANGED")
                if _file_identity(os.fstat(fd)) != identity:
                    raise _Unavailable("OBSERVATION_CHANGED")
            # Negative witnesses follow all directory inspection. Only the
            # selected installation root and its empty releases directory
            # carry content timestamps; shared ancestors may change freely.
            for parent, name in self.absent:
                try:
                    os.stat(name, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                raise _Unavailable("OBSERVATION_CHANGED")
            self._check_directories()
            if self.absent and _file_identity(os.fstat(self.root_fd)) != self.root_contents:
                raise _Unavailable("OBSERVATION_CHANGED")
            for fd, identity in self.empty:
                if _file_identity(os.fstat(fd)) != identity:
                    raise _Unavailable("OBSERVATION_CHANGED")
        except (OSError, _Unavailable):
            raise _Unavailable("OBSERVATION_CHANGED") from None


def _read_fd(fd: int) -> bytes:
    """Read bounded content only after the held descriptor is a regular file.

    NOFOLLOW and NONBLOCK protect the open against symlink and FIFO swaps.
    A regular-file check precedes every content read; no general claim is made
    that opening every possible special device would itself be side-effect free.
    """
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise _Unavailable("METADATA_NOT_REGULAR_FILE")
        if info.st_size > _MAX_METADATA_BYTES:
            raise _Unavailable("METADATA_TOO_LARGE")
        data = bytearray()
        while len(data) <= _MAX_METADATA_BYTES:
            chunk = os.read(fd, min(65536, _MAX_METADATA_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > _MAX_METADATA_BYTES:
            raise _Unavailable("METADATA_TOO_LARGE")
        return bytes(data)
    except OSError:
        raise _Unavailable("METADATA_UNREADABLE") from None


def _loads_object(data: bytes, *, malformed: str) -> dict:
    """Parse one JSON object, refusing duplicate keys and non-object roots."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise _Unavailable(malformed) from None
    try:
        payload = json.loads(text, object_pairs_hook=_object_without_duplicates)
    except ValueError:
        raise _Unavailable(malformed) from None
    if not isinstance(payload, dict):
        raise _Unavailable(malformed)
    return payload


def _object_without_duplicates(pairs):
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
