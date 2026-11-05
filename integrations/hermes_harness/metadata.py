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
        root = _qualified_state_root(root)
        manifest_path = root / "install-manifest.json"
        if not _path_exists(manifest_path):
            # Absence must still hold when the observation ends, and a root
            # that still carries incumbent install evidence is a damaged
            # installation rather than an absent role.
            if _path_exists(manifest_path):
                return _projection(
                    role=expected_role, state=UNAVAILABLE, reason="OBSERVATION_CHANGED",
                )
            if _install_evidence(root):
                return _projection(
                    role=expected_role, state=UNAVAILABLE, reason="MANIFEST_MISSING",
                )
            return _projection(
                role=expected_role, state=ABSENT, reason="INSTALL_MANIFEST_ABSENT",
            )
        observation = _observe(root, expected_role)
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


def _observe(root: Path, role: str) -> dict:
    """Read one installed role's metadata and project it. Raises ``_Unavailable``."""
    from integrations.hermes_models.contract import native_provider
    from integrations.hermes_runtime.profile import load_profile

    manifest_bytes = _read_bounded(
        root / "install-manifest.json",
        missing="MANIFEST_MISSING",
        not_regular="METADATA_NOT_REGULAR_FILE",
        too_large="METADATA_TOO_LARGE",
    )
    manifest = _loads_object(manifest_bytes, malformed="MANIFEST_MALFORMED")
    _assert_manifest(manifest, root, role)

    release_id, release_dir, link_identity = _current_release(root)
    if manifest.get("current_release") != release_id:
        raise _Unavailable("RELEASE_MISMATCH")

    receipt_bytes = _read_bounded(
        release_dir / "install-receipt.json",
        missing="RECEIPT_MISSING",
        not_regular="METADATA_NOT_REGULAR_FILE",
        too_large="METADATA_TOO_LARGE",
    )
    receipt = _loads_object(receipt_bytes, malformed="RECEIPT_MALFORMED")
    _assert_receipt(receipt, role, manifest.get("sha"))

    profile_bytes = _read_bounded(
        release_dir / "profile.yaml",
        missing="PROFILE_MISSING",
        not_regular="METADATA_NOT_REGULAR_FILE",
        too_large="METADATA_TOO_LARGE",
    )
    profile_digest = _sha256(profile_bytes)
    if receipt.get("profile_sha256") != profile_digest:
        raise _Unavailable("PROFILE_DIGEST_MISMATCH")
    try:
        profile = load_profile(release_dir / "profile.yaml")
    except (RuntimeError, OSError, ValueError):
        # The profile owner refuses with its own codes; the facade keeps one
        # fixed reason and never forwards the underlying text.
        raise _Unavailable("PROFILE_UNQUALIFIED") from None
    try:
        profile_after = _read_bounded(
            release_dir / "profile.yaml",
            missing="PROFILE_MISSING",
            not_regular="METADATA_NOT_REGULAR_FILE",
            too_large="METADATA_TOO_LARGE",
        )
    except _Unavailable:
        raise _Unavailable("OBSERVATION_CHANGED") from None
    if _sha256(profile_after) != profile_digest:
        # The profile owner reads the file itself. This detects a change that
        # persists across the read; it cannot detect a change that is undone
        # between the owner's read and this one, so the published digest and
        # the published selection are not cryptographically one snapshot.
        raise _Unavailable("OBSERVATION_CHANGED")
    if profile.role != role or profile.service_name != f"hermes-runtime-{role}":
        raise _Unavailable("PROFILE_ROLE_MISMATCH")
    if profile.sha != manifest.get("sha"):
        raise _Unavailable("MANIFEST_INCONSISTENT")

    config_dir = _require_real_dir_chain(
        release_dir, ("hermes-home", "profiles", role),
        missing="CONFIG_MISSING", invalid="CONFIG_PATH_INVALID",
    )
    config_bytes = _read_bounded(
        config_dir / "config.yaml",
        missing="CONFIG_MISSING",
        not_regular="METADATA_NOT_REGULAR_FILE",
        too_large="METADATA_TOO_LARGE",
    )
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
    _recheck(root, release_dir, role, link_identity, digests)

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
    try:
        if Path(state_value).resolve() != root.resolve():
            raise _Unavailable("MANIFEST_INCONSISTENT")
    except (OSError, ValueError):
        raise _Unavailable("MANIFEST_INCONSISTENT") from None


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


def _recheck(
    root: Path,
    release_dir: Path,
    role: str,
    link_identity: tuple,
    digests: dict,
) -> None:
    """Confirm the current release and its metadata did not move under the read."""
    try:
        _release_id, _release_dir, current_identity = _current_release(root)
        if current_identity != link_identity:
            raise _Unavailable("OBSERVATION_CHANGED")
        config_dir = _require_real_dir_chain(
            release_dir, ("hermes-home", "profiles", role),
            missing="CONFIG_MISSING", invalid="CONFIG_PATH_INVALID",
        )
        again = {
            "manifest": _read_bounded(
                root / "install-manifest.json",
                missing="MANIFEST_MISSING",
                not_regular="METADATA_NOT_REGULAR_FILE",
                too_large="METADATA_TOO_LARGE",
            ),
            "receipt": _read_bounded(
                release_dir / "install-receipt.json",
                missing="RECEIPT_MISSING",
                not_regular="METADATA_NOT_REGULAR_FILE",
                too_large="METADATA_TOO_LARGE",
            ),
            "profile": _read_bounded(
                release_dir / "profile.yaml",
                missing="PROFILE_MISSING",
                not_regular="METADATA_NOT_REGULAR_FILE",
                too_large="METADATA_TOO_LARGE",
            ),
            "config": _read_bounded(
                config_dir / "config.yaml",
                missing="CONFIG_MISSING",
                not_regular="METADATA_NOT_REGULAR_FILE",
                too_large="METADATA_TOO_LARGE",
            ),
        }
    except _Unavailable:
        raise _Unavailable("OBSERVATION_CHANGED") from None
    for key, data in again.items():
        if _sha256(data) != digests[key]:
            raise _Unavailable("OBSERVATION_CHANGED")


def _current_release(root: Path) -> tuple[str, Path, tuple]:
    """Resolve the incumbent current-release link without following it blindly."""
    link = root / "current"
    try:
        info = os.lstat(link)
    except FileNotFoundError:
        raise _Unavailable("CURRENT_LINK_INVALID") from None
    except OSError:
        raise _Unavailable("CURRENT_LINK_UNREADABLE") from None
    if not stat.S_ISLNK(info.st_mode):
        raise _Unavailable("CURRENT_LINK_INVALID")
    try:
        target = os.readlink(link)
    except OSError:
        raise _Unavailable("CURRENT_LINK_UNREADABLE") from None
    match = _CURRENT_TARGET.fullmatch(target)
    if match is None:
        raise _Unavailable("CURRENT_LINK_INVALID")
    release_id = match.group(1)
    release_dir = _require_real_dir_chain(
        root, ("releases", release_id),
        missing="RELEASE_UNAVAILABLE", invalid="RELEASE_UNAVAILABLE",
    )
    identity = (info.st_dev, info.st_ino, info.st_mtime_ns, target)
    return release_id, release_dir, identity


def _qualified_state_root(state: Path) -> Path:
    """Prove the state root is a readable, qualified, non-symlinked directory."""
    try:
        info = os.lstat(state)
    except FileNotFoundError:
        raise _Unavailable("STATE_ROOT_MISSING") from None
    except OSError:
        raise _Unavailable("STATE_ROOT_UNREADABLE") from None
    if stat.S_ISLNK(info.st_mode):
        raise _Unavailable("STATE_ROOT_SYMLINK_REFUSED")
    if not stat.S_ISDIR(info.st_mode):
        raise _Unavailable("STATE_ROOT_NOT_DIRECTORY")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(state, flags)
    except OSError:
        raise _Unavailable("STATE_ROOT_UNREADABLE") from None
    os.close(fd)
    if not _dedicated_root(state):
        raise _Unavailable("STATE_ROOT_NOT_QUALIFIED")
    return state


def _dedicated_root(state: Path) -> bool:
    """A state root must be one dedicated directory, not a shared system path.

    Mirrors the incumbent check in ``hermes_runtime.profile`` so the facade
    cannot report ``ABSENT`` for a broad directory such as ``/tmp``.
    """
    try:
        resolved = state.resolve()
    except (OSError, ValueError):
        return False
    banned = {Path("/"), Path("/tmp"), Path("/var"), Path("/home"), Path("/etc")}
    try:
        home = Path.home()
    except (RuntimeError, OSError):
        home = None
    if home is not None:
        banned.update({home, home / ".config"})
    if resolved in banned:
        return False
    return len(resolved.parts) >= 3


def _require_real_dir_chain(
    base: Path,
    parts: tuple[str, ...],
    *,
    missing: str,
    invalid: str,
) -> Path:
    """Verify every intermediate directory is a real directory, not a symlink.

    ``O_NOFOLLOW`` only protects the final component, so a symlinked
    intermediate directory would otherwise carry the read out of the release.
    """
    current = base
    for part in parts:
        current = current / part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            raise _Unavailable(missing) from None
        except OSError:
            raise _Unavailable(invalid) from None
        if not stat.S_ISDIR(info.st_mode):
            raise _Unavailable(invalid)
    return current


def _path_exists(path: Path) -> bool:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError:
        raise _Unavailable("METADATA_UNREADABLE") from None
    return True


def _install_evidence(root: Path) -> bool:
    """True when the root still carries incumbent installation evidence.

    A root whose manifest is gone but which still has a current-release link
    or a written release is a damaged installation, not an absent role.
    Reporting ``ABSENT`` there would tell a panel that an installed role is
    missing. An empty ``releases`` directory with no current link carries no
    evidence: the incumbent installer removes the whole state directory when a
    first install fails, so such a root is not an installer artefact.
    """
    if _path_exists(root / "current"):
        return True
    releases = root / "releases"
    try:
        info = os.lstat(releases)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    if not stat.S_ISDIR(info.st_mode):
        return True
    try:
        return any(releases.iterdir())
    except OSError:
        return True


def _read_bounded(path: Path, *, missing: str, not_regular: str, too_large: str) -> bytes:
    """Read one regular file through a bound descriptor with a finite byte cap.

    The file type is checked before the open so a fifo or device can never
    block or side-effect the read, and re-checked on the descriptor itself so
    a swap between the check and the open is still refused.
    """
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        raise _Unavailable(missing) from None
    except OSError:
        raise _Unavailable("METADATA_UNREADABLE") from None
    if not stat.S_ISREG(info.st_mode):
        raise _Unavailable(not_regular)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        raise _Unavailable(missing) from None
    except OSError as exc:
        if exc.errno in {getattr(os, "ELOOP", 40), getattr(os, "EMLINK", 31)}:
            raise _Unavailable(not_regular) from None
        raise _Unavailable("METADATA_UNREADABLE") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise _Unavailable(not_regular)
        if info.st_size > _MAX_METADATA_BYTES:
            raise _Unavailable(too_large)
        data = b""
        while len(data) <= _MAX_METADATA_BYTES:
            chunk = os.read(fd, min(65536, _MAX_METADATA_BYTES + 1 - len(data)))
            if not chunk:
                break
            data += chunk
        if len(data) > _MAX_METADATA_BYTES:
            raise _Unavailable(too_large)
        return data
    except OSError:
        raise _Unavailable("METADATA_UNREADABLE") from None
    finally:
        os.close(fd)


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
