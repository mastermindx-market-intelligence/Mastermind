"""Off-host disaster-recovery export, transport, and restore-verification for
the Executive lifecycle database.

This module never replaces or reinterprets ``control_plane.executive_backup``
-- it consumes an already-created, already-verified backup artifact and
manifest verbatim, encrypts it client-side, ships the ciphertext to a
create-only off-host object store, and verifies a fetched copy before restore.

The production Executive runtime executes under ``python3.12 -I -S`` (no
site-packages), so this module imports **stdlib only**, plus the platform
``/usr/bin/openssl`` binary via ``subprocess`` for the symmetric cipher.  The
composition -- encrypt-then-MAC, independent per-export HKDF subkeys, a
closed envelope schema, create-only transports, checksum-after-upload -- is
the reviewed unit, not any single primitive.

Key custody is entirely the caller's responsibility.  This module never
generates, stores, or transmits a *master* key on its own initiative; it only
ever receives one as an in-memory base64 string supplied by the caller (a
CLI reading ``--key-file``/``--key-env``, or a drill's ephemeral
``os.urandom`` key).  No key or transport-token material is ever written into
an envelope, a receipt, a log line, or an exception message.
"""

from __future__ import annotations

import base64
import binascii
import dataclasses
import errno
import hashlib
import hmac
import json
import os
import re
import stat
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from control_plane.executive_backup import (
    BackupVerificationError,
    verify_backup,
)
from control_plane.executive_runtime import RuntimeProofError

EXPORT_ENVELOPE_SCHEMA_VERSION = "mastermind.executive_dr_export/v1"
QUARANTINE_RECEIPT_SCHEMA_VERSION = "mastermind.executive_dr_quarantine_receipt/v1"

CIPHER_LABEL = "aes-256-ctr+hmac-sha256"
KDF_LABEL = "hkdf-sha256"
OPENSSL_KDF_LABEL = "pbkdf2-sha256-600000"
_NONCE_NOTE = (
    "CTR IV/nonce derivation is internal to openssl's -pbkdf2 key derivation "
    "for this cipher mode; no separate nonce field is carried."
)

# Injection seam for the openssl binary (adversarial review B1): the default
# below is used unless a caller passes `openssl_binary=` explicitly or the
# environment variable MASTERMIND_DR_OPENSSL is set. Ops uses the env var to
# pin a specific binary on a host; tests use the explicit parameter to run
# the SAME export through two different openssl families in one process.
_DEFAULT_OPENSSL_BINARY = "/usr/bin/openssl"
_OPENSSL_BINARY_ENV = "MASTERMIND_DR_OPENSSL"
_PBKDF2_ITERATIONS = 600_000
_HKDF_CIPHER_INFO = b"mastermind-dr-cipher-v1"
_HKDF_MAC_INFO = b"mastermind-dr-mac-v1"
_HKDF_SALT_BYTES = 16
# The classic openssl `enc -S` salt is 8 bytes -- PKCS5_SALT_LEN, a fixed
# constant of the traditional OpenSSL/LibreSSL EVP_BytesToKey-family salted
# format, not a LibreSSL-specific limit (LibreSSL 3.3.6 does reject a
# 16-byte hex salt with "hex string is too long", but the 8-byte width
# itself is the shared, decades-old convention both implementations honor).
_OPENSSL_SALT_BYTES = 8
# The traditional "Salted__<8-byte-salt>" magic header (adversarial review
# B1): LibreSSL (macOS system /usr/bin/openssl, verified 3.3.6) WRITES this
# 16-byte header even when `-S` supplies the salt explicitly; OpenSSL 3.x
# (verified 3.6.3 and 3.0.13) OMITS it under the byte-identical invocation --
# the PBKDF2 key+IV derivation itself is identical between the two (cipher
# bodies match once the header is stripped), only the header differs. Left
# unhandled, an export encrypted on macOS is undecryptable by a Linux CI
# drill runner and vice versa. The STORED/shipped/MAC'd ciphertext is
# therefore always normalized to the headerless form regardless of which
# local binary produced it; a header-writing binary needs the header
# stripped after encrypt and re-prepended before decrypt (see
# `_detect_salted_header_family`, `_normalize_openssl_ciphertext`,
# `_prepare_decrypt_input`).
_SALTED_MAGIC = b"Salted__"
_SALTED_HEADER_LEN = 8 + _OPENSSL_SALT_BYTES
_HEADER_FAMILY_CACHE: dict[str, bool] = {}
_MAX_ENVELOPE_BYTES = 64 * 1024
_MAX_RELEASE_BODY_BYTES = 256 * 1024

_EXPORT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_LABEL_RE = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")

_ENVELOPE_FIELDS = frozenset(
    {
        "schema_version",
        "export_id",
        "created_at",
        "backup_manifest",
        "cipher",
        "kdf",
        "salt_b64",
        "nonce_note",
        "openssl_kdf",
        "openssl_salt_b64",
        "key_id",
        "mac_b64",
        "plaintext_sha256",
        "ciphertext_sha256",
        "byte_size",
        "source_release_commit",
        "transport_target",
        "retention_class",
    }
)


class ExecutiveDRError(RuntimeProofError):
    """Base class for operator-visible DR export/transport/restore failures."""


class DRFailureState(str, Enum):
    """Typed failure states.  Superset of the DR-C0 packet §10 catalog.

    The packet's list ends in "..." (explicitly non-exhaustive).  Four
    members below (``KEY_INVALID``, ``ENVELOPE_INVALID``, ``MAC_MISMATCH``,
    ``OUTPUT_CONFLICT``) are additions this build needed for envelope
    structural validation and local I/O safety that the packet's illustrative
    list did not itemize; every packet-named state is reused verbatim.
    """

    NO_BACKUP = "NO_BACKUP"
    STALE = "STALE"
    LOCAL_CORRUPT = "LOCAL_CORRUPT"
    OFFHOST_ABSENT = "OFFHOST_ABSENT"
    REMOTE_DIGEST_CONFLICT = "REMOTE_DIGEST_CONFLICT"
    CREDENTIAL_LOST = "CREDENTIAL_LOST"
    KEY_LOST = "KEY_LOST"
    KEY_INVALID = "KEY_INVALID"
    REMOTE_UNAVAILABLE = "REMOTE_UNAVAILABLE"
    QUOTA_FULL = "QUOTA_FULL"
    UPLOAD_EFFECT_UNKNOWN = "UPLOAD_EFFECT_UNKNOWN"
    PARTIAL_CHAIN = "PARTIAL_CHAIN"
    POINT_AMBIGUOUS = "POINT_AMBIGUOUS"
    RELEASE_SCHEMA_MISMATCH = "RELEASE_SCHEMA_MISMATCH"
    VERIFIER_UNAVAILABLE = "VERIFIER_UNAVAILABLE"
    SERVICE_MARKER_LIVE = "SERVICE_MARKER_LIVE"
    DISK_INSUFFICIENT = "DISK_INSUFFICIENT"
    ROLLBACK_UNAVAILABLE = "ROLLBACK_UNAVAILABLE"
    ENVELOPE_INVALID = "ENVELOPE_INVALID"
    MAC_MISMATCH = "MAC_MISMATCH"
    OUTPUT_CONFLICT = "OUTPUT_CONFLICT"


class ExecutiveDRTypedError(ExecutiveDRError):
    """Every raised DR error carries a closed, typed ``state``."""

    def __init__(self, state: DRFailureState, message: str) -> None:
        super().__init__(f"[{state.value}] {message}")
        self.state = state


# --------------------------------------------------------------------------
# Small private-file helpers (deliberately duplicated from
# control_plane.executive_backup's style rather than imported: this module
# is meant to stand alone against that module's private surface, and the
# duplicated helpers are each under fifteen lines).
# --------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _ensure_private_directory(path: Path) -> Path:
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = path.lstat()
    except OSError as exc:
        raise ExecutiveDRError(f"cannot prepare private DR directory: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ExecutiveDRError(f"DR path is not a real directory: {path}")
    if info.st_uid != os.geteuid():
        raise ExecutiveDRError(f"DR directory is not owned by the control principal: {path}")
    try:
        path.chmod(0o700)
    except OSError as exc:
        raise ExecutiveDRError(f"cannot protect DR directory: {exc}") from exc
    return path.resolve(strict=True)


def _assert_private_regular_file(path: Path, *, label: str) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as exc:
        raise ExecutiveDRTypedError(DRFailureState.LOCAL_CORRUPT, f"{label} is unavailable: {exc}") from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ExecutiveDRTypedError(DRFailureState.LOCAL_CORRUPT, f"{label} must be a single-link regular file")
    if info.st_uid != os.geteuid():
        raise ExecutiveDRTypedError(DRFailureState.LOCAL_CORRUPT, f"{label} is not owned by the control principal")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise ExecutiveDRTypedError(DRFailureState.LOCAL_CORRUPT, f"{label} is accessible to group or other")
    return info


def _fsync_path(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _reraise_enospc_as_typed(exc: OSError) -> None:
    if exc.errno == errno.ENOSPC:
        raise ExecutiveDRTypedError(DRFailureState.DISK_INSUFFICIENT, "not enough free disk space for a DR write") from exc


def _write_private_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0), 0o600)
    try:
        view = memoryview(payload)
        while view:
            try:
                written = os.write(descriptor, view)
            except OSError as exc:
                _reraise_enospc_as_typed(exc)
                raise
            if written <= 0:  # pragma: no cover - defensive OS boundary
                raise OSError("short write while persisting a DR file")
            view = view[written:]
        try:
            os.fsync(descriptor)
        except OSError as exc:
            _reraise_enospc_as_typed(exc)
            raise
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def _copy_private_file(source: Path, destination: Path) -> None:
    _assert_private_regular_file(source, label="DR source file")
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0), 0o600)
    try:
        with source.open("rb") as input_handle, os.fdopen(descriptor, "wb", closefd=False) as output:
            for block in iter(lambda: input_handle.read(1024 * 1024), b""):
                try:
                    output.write(block)
                except OSError as exc:
                    _reraise_enospc_as_typed(exc)
                    raise
            output.flush()
            os.fsync(descriptor)
    except Exception:
        try:
            destination.unlink()
        except OSError:
            pass
        raise
    finally:
        os.close(descriptor)


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stream_sha256_and_mac(path: Path, mac_obj: Any | None) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
            if mac_obj is not None:
                mac_obj.update(block)
            size += len(block)
    return digest.hexdigest(), size


# --------------------------------------------------------------------------
# Crypto: independent HKDF-SHA256 subkey derivation + openssl composition.
# --------------------------------------------------------------------------


def _hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    return hmac.new(salt, ikm, hashlib.sha256).digest()


def _hkdf_expand_one_block(prk: bytes, info: bytes) -> bytes:
    # A single HKDF-expand block yields 32 bytes -- exactly what every
    # subkey in this module needs (SHA-256 digest size), so T(1) suffices.
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()


def _derive_subkeys(master_key: bytes, salt: bytes) -> tuple[bytes, bytes]:
    prk = _hkdf_extract(salt, master_key)
    cipher_subkey = _hkdf_expand_one_block(prk, _HKDF_CIPHER_INFO)
    mac_subkey = _hkdf_expand_one_block(prk, _HKDF_MAC_INFO)
    return cipher_subkey, mac_subkey


def _decode_master_key(master_key_b64: str) -> bytes:
    if not isinstance(master_key_b64, str) or not master_key_b64:
        raise ExecutiveDRTypedError(DRFailureState.KEY_INVALID, "DR master key must be a non-empty string")
    try:
        key = base64.b64decode(master_key_b64, validate=True)
    except (binascii.Error, ValueError):
        raise ExecutiveDRTypedError(DRFailureState.KEY_INVALID, "DR master key is not valid base64") from None
    if len(key) != 32:
        raise ExecutiveDRTypedError(DRFailureState.KEY_INVALID, "DR master key must decode to exactly 32 bytes")
    return key


def resolve_openssl_binary(openssl_binary: str | None = None) -> str:
    """Injection seam order: explicit parameter > MASTERMIND_DR_OPENSSL > default."""

    if openssl_binary:
        return openssl_binary
    return os.environ.get(_OPENSSL_BINARY_ENV) or _DEFAULT_OPENSSL_BINARY


def _detect_salted_header_family(binary: str) -> bool:
    """Feature-detect ONCE per process per binary path (adversarial review B1).

    Encrypts a fixed 1-byte input with a throwaway, non-secret pass/salt at
    minimum PBKDF2 cost and observes whether the output begins with the
    traditional ``Salted__`` magic. Deterministic and cheap (~1ms); never a
    try-and-retry against the real export.
    """

    cached = _HEADER_FAMILY_CACHE.get(binary)
    if cached is not None:
        return cached
    if not os.path.exists(binary):
        raise ExecutiveDRTypedError(DRFailureState.VERIFIER_UNAVAILABLE, f"system openssl binary is unavailable: {binary}")
    command = [
        binary, "enc", "-aes-256-ctr", "-e",
        "-pass", "pass:mastermind-dr-header-probe",  # fixed, non-secret, never real key material
        "-pbkdf2", "-iter", "1", "-md", "sha256",
        "-S", "00" * _OPENSSL_SALT_BYTES,
    ]
    try:
        completed = subprocess.run(command, input=b"x", capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ExecutiveDRTypedError(DRFailureState.VERIFIER_UNAVAILABLE, f"system openssl header-family probe could not be invoked: {binary}") from None
    if completed.returncode != 0:
        detail = completed.stderr[:512].decode("utf-8", errors="replace").strip()
        raise ExecutiveDRTypedError(
            DRFailureState.VERIFIER_UNAVAILABLE,
            f"system openssl header-family probe exited {completed.returncode}: {detail}" if detail else
            f"system openssl header-family probe exited {completed.returncode}",
        )
    family = completed.stdout[: len(_SALTED_MAGIC)] == _SALTED_MAGIC
    _HEADER_FAMILY_CACHE[binary] = family
    return family


def _normalize_openssl_ciphertext(path: Path, *, header_family: bool, expected_salt: bytes) -> None:
    """After encrypt: strip a header-writing binary's Salted__ header in place.

    The stored/shipped/MAC'd ciphertext is always the HEADERLESS form,
    regardless of which local openssl family produced it -- see the
    `_SALTED_MAGIC` module docstring block for why.
    """

    if not header_family:
        return
    with path.open("rb") as handle:
        header = handle.read(_SALTED_HEADER_LEN)
    if len(header) != _SALTED_HEADER_LEN or header[: len(_SALTED_MAGIC)] != _SALTED_MAGIC:
        raise ExecutiveDRTypedError(
            DRFailureState.LOCAL_CORRUPT,
            "openssl was detected as header-writing but did not write the expected Salted__ header",
        )
    if header[len(_SALTED_MAGIC) :] != expected_salt:
        raise ExecutiveDRTypedError(
            DRFailureState.LOCAL_CORRUPT,
            "openssl wrote a header salt that does not match the requested -S salt",
        )
    temp = path.with_name(f".{path.name}.strip.tmp")
    descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0), 0o600)
    try:
        with path.open("rb") as source, os.fdopen(descriptor, "wb", closefd=False) as dest:
            source.seek(_SALTED_HEADER_LEN)
            for block in iter(lambda: source.read(1024 * 1024), b""):
                dest.write(block)
            dest.flush()
            os.fsync(descriptor)
    except Exception:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
        raise
    finally:
        os.close(descriptor)
    os.replace(temp, path)


def _prepare_decrypt_input(ciphertext_path: Path, *, header_family: bool, salt: bytes, work_dir: Path) -> Path:
    """Before decrypt: if the LOCAL binary expects a header, build a temp
    input with `Salted__<salt>` re-prepended (the stored ciphertext is
    always headerless); a headerless-family binary decrypts the stored
    bytes directly."""

    if not header_family:
        return ciphertext_path
    prefixed = work_dir / f".{ciphertext_path.name}.headered.tmp"
    descriptor = os.open(prefixed, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0), 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as dest, ciphertext_path.open("rb") as source:
            dest.write(_SALTED_MAGIC + salt)
            for block in iter(lambda: source.read(1024 * 1024), b""):
                dest.write(block)
            dest.flush()
            os.fsync(descriptor)
    except Exception:
        try:
            prefixed.unlink()
        except FileNotFoundError:
            pass
        raise
    finally:
        os.close(descriptor)
    return prefixed


def _run_openssl(args: list[str], *, binary: str, env: Mapping[str, str], input_path: Path, output_path: Path) -> None:
    if not os.path.exists(binary):
        raise ExecutiveDRTypedError(DRFailureState.VERIFIER_UNAVAILABLE, f"system openssl binary is unavailable: {binary}")
    command = [binary, "enc", *args, "-in", str(input_path), "-out", str(output_path)]
    try:
        completed = subprocess.run(
            command,
            env=dict(env),
            check=False,
            capture_output=True,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired):
        # The passphrase crosses only via the child's environment (never
        # argv), so subprocess stderr cannot echo it back -- unlike the
        # OSError/TimeoutExpired branch (which carries no process output at
        # all and stays a static message), a genuine non-zero exit below DOES
        # forward a length-capped stderr excerpt: suppressing it protects
        # nothing here and blinds the disaster-recovery operator (M3).
        raise ExecutiveDRTypedError(DRFailureState.VERIFIER_UNAVAILABLE, "system openssl could not be invoked") from None
    if completed.returncode != 0:
        detail = completed.stderr[:512].decode("utf-8", errors="replace").strip()
        message = f"system openssl exited {completed.returncode}: {detail}" if detail else f"system openssl exited {completed.returncode} with no stderr"
        raise ExecutiveDRTypedError(DRFailureState.LOCAL_CORRUPT, message)


# --------------------------------------------------------------------------
# Envelope: closed-set load/validate, canonicalization, MAC coverage.
# --------------------------------------------------------------------------


def _no_dup_pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values:
        if key in result:
            raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, f"DR export envelope has duplicate key {key!r}")
        result[key] = value
    return result


def _validate_envelope_fields(value: Mapping[str, Any]) -> None:
    if set(value) != _ENVELOPE_FIELDS:
        missing = sorted(_ENVELOPE_FIELDS - set(value))
        unknown = sorted(set(value) - _ENVELOPE_FIELDS)
        raise ExecutiveDRTypedError(
            DRFailureState.ENVELOPE_INVALID,
            f"DR export envelope field set drifted; missing={missing}, unknown={unknown}",
        )
    if value.get("schema_version") != EXPORT_ENVELOPE_SCHEMA_VERSION:
        raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, "DR export envelope schema version is unsupported")
    if not isinstance(value.get("export_id"), str) or not _EXPORT_ID_RE.fullmatch(value["export_id"]):
        raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, "DR export id is invalid")
    if not isinstance(value.get("created_at"), str) or not value["created_at"]:
        raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, "DR export creation time is invalid")
    try:
        datetime.fromisoformat(value["created_at"])
    except ValueError:
        raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, "DR export creation time is not ISO-8601") from None
    if not isinstance(value.get("backup_manifest"), dict) or not value["backup_manifest"]:
        raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, "DR export embedded backup manifest is invalid")
    if value.get("cipher") != CIPHER_LABEL:
        raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, "DR export cipher label is unsupported")
    if value.get("kdf") != KDF_LABEL:
        raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, "DR export KDF label is unsupported")
    if value.get("openssl_kdf") != OPENSSL_KDF_LABEL:
        raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, "DR export openssl KDF label is unsupported")
    if not isinstance(value.get("nonce_note"), str) or not value["nonce_note"]:
        raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, "DR export nonce note is invalid")
    for name in ("salt_b64", "openssl_salt_b64", "mac_b64"):
        candidate = value.get(name)
        if not isinstance(candidate, str) or not candidate:
            raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, f"DR export {name} is invalid")
        try:
            base64.b64decode(candidate, validate=True)
        except (binascii.Error, ValueError):
            raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, f"DR export {name} is not valid base64") from None
    for name in ("plaintext_sha256", "ciphertext_sha256"):
        candidate = value.get(name)
        if not isinstance(candidate, str) or not _HASH_RE.fullmatch(candidate):
            raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, f"DR export {name} is invalid")
    byte_size = value.get("byte_size")
    if isinstance(byte_size, bool) or not isinstance(byte_size, int) or byte_size <= 0:
        raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, "DR export byte_size is invalid")
    if not isinstance(value.get("source_release_commit"), str) or not _GIT_SHA_RE.fullmatch(value["source_release_commit"]):
        raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, "DR export source_release_commit is invalid")
    for name in ("key_id", "transport_target", "retention_class"):
        candidate = value.get(name)
        if not isinstance(candidate, str) or not _LABEL_RE.fullmatch(candidate):
            raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, f"DR export {name} is invalid")


def _load_envelope(path: Path) -> dict[str, Any]:
    candidate = Path(path).expanduser()
    _assert_private_regular_file(candidate, label="DR export envelope")
    resolved = candidate.resolve(strict=True)
    info = _assert_private_regular_file(resolved, label="DR export envelope")
    if info.st_size <= 0 or info.st_size > _MAX_ENVELOPE_BYTES:
        raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, "DR export envelope is empty or exceeds 64 KiB")
    raw = resolved.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=_no_dup_pairs)
    except ExecutiveDRTypedError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, f"DR export envelope is not strict UTF-8 JSON: {exc}") from None
    if not isinstance(value, dict):
        raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, "DR export envelope root must be an object")
    _validate_envelope_fields(value)
    return value


def _canonical_envelope_without_mac(envelope: Mapping[str, Any]) -> bytes:
    reduced = {key: value for key, value in envelope.items() if key != "mac_b64"}
    return json.dumps(reduced, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _assert_ciphertext_matches_envelope(path: Path, envelope: Mapping[str, Any]) -> None:
    info = _assert_private_regular_file(Path(path).expanduser().resolve(strict=True), label="DR ciphertext")
    if info.st_size != envelope["byte_size"]:
        raise ExecutiveDRTypedError(DRFailureState.LOCAL_CORRUPT, "DR ciphertext size differs from its envelope")
    if _sha256_path(Path(path)) != envelope["ciphertext_sha256"]:
        raise ExecutiveDRTypedError(DRFailureState.LOCAL_CORRUPT, "DR ciphertext digest differs from its envelope")


def _compact_stamp(created_at_iso: str) -> str:
    parsed = datetime.fromisoformat(created_at_iso)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _export_tag(envelope: Mapping[str, Any]) -> str:
    return f"dr-export/{_compact_stamp(str(envelope['created_at']))}-{envelope['export_id']}"


# --------------------------------------------------------------------------
# Public dataclasses.
# --------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ExportReceipt:
    export_id: str
    created_at: str
    envelope_path: str
    ciphertext_path: str
    ciphertext_sha256: str
    plaintext_sha256: str
    byte_size: int
    key_id: str
    transport_target: str
    retention_class: str
    source_release_commit: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class DecryptReceipt:
    export_id: str
    output_path: str
    plaintext_sha256: str
    byte_size: int

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class EnvelopeVerification:
    export_id: str
    schema_version: str
    ciphertext_sha256: str
    byte_size: int
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class ShipReceipt:
    export_id: str
    tag: str
    transport: str
    duplicate: bool
    ciphertext_sha256: str
    byte_size: int
    remote_ref: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class FetchReceipt:
    export_id: str
    tag: str
    transport: str
    ciphertext_path: str
    envelope_path: str
    ciphertext_sha256: str
    byte_size: int
    remote_ref: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class QuarantineReceipt:
    original_path: str
    quarantined_path: str
    receipt_path: str
    reason: str
    quarantined_at: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


# --------------------------------------------------------------------------
# Quarantine (corrupt/unverifiable local artifacts are renamed, never
# deleted).
# --------------------------------------------------------------------------


def quarantine_artifact(path: str | Path, *, reason: str) -> QuarantineReceipt:
    source = Path(path).expanduser()
    info = source.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ExecutiveDRError(f"refuse to quarantine a non-regular-file path: {source}")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = source.with_name(f"{source.name}.quarantined-{stamp}")
    if target.exists():
        raise ExecutiveDRError(f"quarantine target already exists: {target}")
    os.replace(source, target)
    _fsync_directory(target.parent)
    receipt_path = target.with_name(f"{target.name}.quarantine-receipt.json")
    quarantined_at = _utc_now()
    _write_private_json(
        receipt_path,
        {
            "schema_version": QUARANTINE_RECEIPT_SCHEMA_VERSION,
            "original_path": str(source),
            "quarantined_path": str(target),
            "reason": reason,
            "quarantined_at": quarantined_at,
        },
    )
    return QuarantineReceipt(
        original_path=str(source),
        quarantined_path=str(target),
        receipt_path=str(receipt_path),
        reason=reason,
        quarantined_at=quarantined_at,
    )


# --------------------------------------------------------------------------
# encrypt_export / decrypt_export / verify_export_envelope
# --------------------------------------------------------------------------


def encrypt_export(
    artifact_path: str | Path,
    manifest_path: str | Path,
    master_key_b64: str,
    staging_dir: str | Path,
    *,
    transport_target: str,
    retention_class: str,
    source_release_commit: str,
    key_id: str = "v1",
    openssl_binary: str | None = None,
) -> ExportReceipt:
    """Verify, then client-side encrypt-then-MAC, an existing local backup."""

    binary = resolve_openssl_binary(openssl_binary)
    header_family = _detect_salted_header_family(binary)

    for label, candidate in (
        ("transport_target", transport_target),
        ("retention_class", retention_class),
        ("key_id", key_id),
    ):
        if not isinstance(candidate, str) or not _LABEL_RE.fullmatch(candidate):
            raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, f"{label} must be a bounded lowercase label")
    if not isinstance(source_release_commit, str) or not _GIT_SHA_RE.fullmatch(source_release_commit):
        raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, "source_release_commit must be a 40-character git sha")

    try:
        verification = verify_backup(artifact_path, manifest_path)
    except BackupVerificationError as exc:
        raise ExecutiveDRTypedError(DRFailureState.LOCAL_CORRUPT, f"backup failed verification before export: {exc}") from None
    if verification.manifest_path is None:
        raise ExecutiveDRTypedError(DRFailureState.NO_BACKUP, "export requires a verified backup manifest")

    manifest_bytes = Path(verification.manifest_path).read_bytes()
    try:
        backup_manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ExecutiveDRTypedError(DRFailureState.LOCAL_CORRUPT, "backup manifest is not valid JSON") from None

    master_key = _decode_master_key(master_key_b64)
    destination = _ensure_private_directory(Path(staging_dir).expanduser())
    export_id = uuid4().hex
    created_at = _utc_now()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base_name = f"executive-dr-{stamp}-{export_id}"
    ciphertext_path = destination / f"{base_name}.sqlite3.enc"
    envelope_path = destination / f"{base_name}.envelope.json"
    temp_cipher = destination / f".{ciphertext_path.name}.tmp"

    salt = os.urandom(_HKDF_SALT_BYTES)
    openssl_salt = os.urandom(_OPENSSL_SALT_BYTES)
    cipher_subkey, mac_subkey = _derive_subkeys(master_key, salt)

    descriptor = os.open(temp_cipher, os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0), 0o600)
    os.close(descriptor)
    try:
        env = {"PATH": "/usr/bin:/bin", "MASTERMIND_DR_PASS": base64.b64encode(cipher_subkey).decode("ascii")}
        _run_openssl(
            [
                "-aes-256-ctr",
                "-e",
                "-pass",
                "env:MASTERMIND_DR_PASS",
                "-pbkdf2",
                "-iter",
                str(_PBKDF2_ITERATIONS),
                "-md",
                "sha256",
                "-S",
                openssl_salt.hex(),
            ],
            binary=binary,
            env=env,
            input_path=Path(verification.database_path),
            output_path=temp_cipher,
        )
        temp_cipher.chmod(0o600)
        _fsync_path(temp_cipher)
        # Normalize to the headerless STORED form regardless of which local
        # openssl family produced the file (adversarial review B1).
        _normalize_openssl_ciphertext(temp_cipher, header_family=header_family, expected_salt=openssl_salt)
        _fsync_path(temp_cipher)
        ciphertext_sha256, byte_size = _stream_sha256_and_mac(temp_cipher, None)
        if byte_size <= 0:
            raise ExecutiveDRTypedError(DRFailureState.LOCAL_CORRUPT, "openssl produced an empty ciphertext")

        envelope_without_mac: dict[str, Any] = {
            "schema_version": EXPORT_ENVELOPE_SCHEMA_VERSION,
            "export_id": export_id,
            "created_at": created_at,
            "backup_manifest": backup_manifest,
            "cipher": CIPHER_LABEL,
            "kdf": KDF_LABEL,
            "salt_b64": base64.b64encode(salt).decode("ascii"),
            "nonce_note": _NONCE_NOTE,
            "openssl_kdf": OPENSSL_KDF_LABEL,
            "openssl_salt_b64": base64.b64encode(openssl_salt).decode("ascii"),
            "key_id": key_id,
            "plaintext_sha256": verification.database_sha256,
            "ciphertext_sha256": ciphertext_sha256,
            "byte_size": byte_size,
            "source_release_commit": source_release_commit,
            "transport_target": transport_target,
            "retention_class": retention_class,
        }
        canonical = json.dumps(envelope_without_mac, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        mac_obj = hmac.new(mac_subkey, canonical, hashlib.sha256)
        with temp_cipher.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                mac_obj.update(block)
        envelope = {**envelope_without_mac, "mac_b64": base64.b64encode(mac_obj.digest()).decode("ascii")}
        _validate_envelope_fields(envelope)

        os.replace(temp_cipher, ciphertext_path)
        _fsync_directory(destination)
        _write_private_json(envelope_path, envelope)
    except Exception:
        for cleanup_path in (temp_cipher, ciphertext_path, envelope_path):
            try:
                cleanup_path.unlink()
            except FileNotFoundError:
                pass
        raise

    return ExportReceipt(
        export_id=export_id,
        created_at=created_at,
        envelope_path=str(envelope_path),
        ciphertext_path=str(ciphertext_path),
        ciphertext_sha256=ciphertext_sha256,
        plaintext_sha256=verification.database_sha256,
        byte_size=byte_size,
        key_id=key_id,
        transport_target=transport_target,
        retention_class=retention_class,
        source_release_commit=source_release_commit,
    )


def decrypt_export(
    ciphertext_path: str | Path,
    envelope_path: str | Path,
    master_key_b64: str,
    output_path: str | Path,
    *,
    openssl_binary: str | None = None,
) -> DecryptReceipt:
    """Verify the MAC, then decrypt.  Zero plaintext output on any failure."""

    binary = resolve_openssl_binary(openssl_binary)
    ciphertext_path = Path(ciphertext_path).expanduser()
    envelope_path = Path(envelope_path).expanduser()
    output_path = Path(output_path).expanduser()
    if os.path.lexists(output_path):
        raise ExecutiveDRTypedError(DRFailureState.OUTPUT_CONFLICT, "decrypt output path already exists")

    envelope = _load_envelope(envelope_path)
    master_key = _decode_master_key(master_key_b64)
    try:
        salt = base64.b64decode(envelope["salt_b64"], validate=True)
        openssl_salt = base64.b64decode(envelope["openssl_salt_b64"], validate=True)
    except (binascii.Error, ValueError):
        raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, "DR export salt is not valid base64") from None
    cipher_subkey, mac_subkey = _derive_subkeys(master_key, salt)

    resolved_ciphertext = Path(ciphertext_path)
    if not os.path.lexists(resolved_ciphertext):
        raise ExecutiveDRTypedError(DRFailureState.OFFHOST_ABSENT, "DR ciphertext file is missing")

    canonical = _canonical_envelope_without_mac(envelope)
    mac_obj = hmac.new(mac_subkey, canonical, hashlib.sha256)
    ciphertext_digest, ciphertext_size = _stream_sha256_and_mac(resolved_ciphertext, mac_obj)
    computed_mac = mac_obj.digest()
    try:
        expected_mac = base64.b64decode(envelope["mac_b64"], validate=True)
    except (binascii.Error, ValueError):
        raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, "DR export mac_b64 is not valid base64") from None

    # MAC first -- wrong key, truncation, a bit-flip, and envelope
    # substitution all land here, before openssl or the output path exist.
    if not hmac.compare_digest(computed_mac, expected_mac):
        raise ExecutiveDRTypedError(DRFailureState.MAC_MISMATCH, "export authentication failed; refusing to decrypt")
    if ciphertext_digest != envelope["ciphertext_sha256"] or ciphertext_size != envelope["byte_size"]:
        raise ExecutiveDRTypedError(
            DRFailureState.MAC_MISMATCH, "ciphertext digest/size differs from the authenticated envelope"
        )

    header_family = _detect_salted_header_family(binary)
    temp_output = output_path.with_name(f".{output_path.name}.tmp")
    descriptor = os.open(temp_output, os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0), 0o600)
    os.close(descriptor)
    decrypt_input: Path | None = None
    try:
        # The stored ciphertext is always headerless; a header-writing local
        # binary needs `Salted__<salt>` re-prepended before it will decrypt
        # (adversarial review B1) -- deterministic, feature-detected once.
        decrypt_input = _prepare_decrypt_input(
            resolved_ciphertext, header_family=header_family, salt=openssl_salt, work_dir=output_path.parent
        )
        env = {"PATH": "/usr/bin:/bin", "MASTERMIND_DR_PASS": base64.b64encode(cipher_subkey).decode("ascii")}
        _run_openssl(
            [
                "-aes-256-ctr",
                "-d",
                "-pass",
                "env:MASTERMIND_DR_PASS",
                "-pbkdf2",
                "-iter",
                str(_PBKDF2_ITERATIONS),
                "-md",
                "sha256",
                "-S",
                openssl_salt.hex(),
            ],
            binary=binary,
            env=env,
            input_path=decrypt_input,
            output_path=temp_output,
        )
        temp_output.chmod(0o600)
        _fsync_path(temp_output)
        plaintext_digest, plaintext_size = _stream_sha256_and_mac(temp_output, None)
        if plaintext_digest != envelope["plaintext_sha256"]:
            raise ExecutiveDRTypedError(
                DRFailureState.LOCAL_CORRUPT, "decrypted plaintext digest differs from the authenticated envelope"
            )
        os.replace(temp_output, output_path)
        _fsync_directory(output_path.parent)
    except Exception:
        for cleanup_path in (temp_output, output_path):
            try:
                cleanup_path.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        if decrypt_input is not None and decrypt_input != resolved_ciphertext:
            try:
                decrypt_input.unlink()
            except FileNotFoundError:
                pass

    return DecryptReceipt(
        export_id=str(envelope["export_id"]),
        output_path=str(output_path),
        plaintext_sha256=plaintext_digest,
        byte_size=plaintext_size,
    )


def verify_export_envelope(
    envelope_path: str | Path, ciphertext_path: str | Path | None = None
) -> EnvelopeVerification:
    """Offline structural + digest check.  Never requires the master key."""

    envelope = _load_envelope(Path(envelope_path))
    if ciphertext_path is not None:
        _assert_ciphertext_matches_envelope(Path(ciphertext_path), envelope)
    return EnvelopeVerification(
        export_id=str(envelope["export_id"]),
        schema_version=str(envelope["schema_version"]),
        ciphertext_sha256=str(envelope["ciphertext_sha256"]),
        byte_size=int(envelope["byte_size"]),
        created_at=str(envelope["created_at"]),
    )


def read_export_backup_manifest(envelope_path: str | Path) -> dict[str, Any]:
    """Return the embedded ``mastermind.executive_backup_manifest/v1`` payload.

    Lets a caller (the CLI's ``restore-verify``, the clean-host drill) write
    the original backup manifest back out to a file and hand it to the
    existing ``verify_restore_drill`` for the exact same manifest cross-check
    a live restore would perform -- without a second manifest schema.
    """

    envelope = _load_envelope(Path(envelope_path))
    manifest = envelope["backup_manifest"]
    if not isinstance(manifest, dict):  # guaranteed by _validate_envelope_fields; defense in depth
        raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, "DR export embedded backup manifest is not an object")
    database = manifest.get("database")
    filename = database.get("filename") if isinstance(database, dict) else None
    if (
        not isinstance(filename, str)
        or not filename
        or filename in (".", "..")
        or "/" in filename
        or "\\" in filename
        or os.path.basename(filename) != filename
    ):
        raise ExecutiveDRTypedError(
            DRFailureState.ENVELOPE_INVALID, "DR export embedded manifest database filename is not a bare basename"
        )
    return manifest


# --------------------------------------------------------------------------
# Directory transport (create-only local filesystem object store; used by
# the offline drill lane and by tests -- zero network dependency).
# --------------------------------------------------------------------------


def ship_export_directory(
    ciphertext_path: str | Path, envelope_path: str | Path, *, directory: str | Path
) -> ShipReceipt:
    store = _ensure_private_directory(Path(directory).expanduser())
    envelope = _load_envelope(Path(envelope_path))
    _assert_ciphertext_matches_envelope(Path(ciphertext_path), envelope)
    tag = _export_tag(envelope)
    object_stem = tag.replace("/", "__")
    dest_cipher = store / f"{object_stem}.sqlite3.enc"
    dest_envelope = store / f"{object_stem}.envelope.json"

    envelope_exists = os.path.lexists(dest_envelope)
    cipher_exists = os.path.lexists(dest_cipher)

    if envelope_exists:
        existing = _load_envelope(dest_envelope)
        if existing.get("ciphertext_sha256") != envelope["ciphertext_sha256"]:
            raise ExecutiveDRTypedError(
                DRFailureState.REMOTE_DIGEST_CONFLICT,
                f"directory transport envelope already exists for tag {tag} with a different export",
            )
        # Adversarial review M1: a matching envelope alone is NOT proof of a
        # duplicate -- the envelope could exist while its ciphertext object
        # is missing (partial prior write) or corrupted. Re-hash the actual
        # remote bytes before ever reporting success.
        if not cipher_exists:
            raise ExecutiveDRTypedError(
                DRFailureState.OFFHOST_ABSENT,
                f"directory transport envelope exists for tag {tag} but its ciphertext object is missing",
            )
        remote_digest = _sha256_path(dest_cipher)
        if remote_digest != envelope["ciphertext_sha256"]:
            raise ExecutiveDRTypedError(
                DRFailureState.REMOTE_DIGEST_CONFLICT,
                f"directory transport ciphertext for tag {tag} does not hash to its own envelope's digest",
            )
        return ShipReceipt(
            export_id=str(envelope["export_id"]),
            tag=tag,
            transport="directory",
            duplicate=True,
            ciphertext_sha256=str(envelope["ciphertext_sha256"]),
            byte_size=int(envelope["byte_size"]),
            remote_ref=str(dest_cipher),
        )
    if cipher_exists:
        raise ExecutiveDRTypedError(
            DRFailureState.REMOTE_DIGEST_CONFLICT,
            f"directory transport ciphertext already exists for tag {tag} without a matching envelope",
        )

    _copy_private_file(Path(ciphertext_path), dest_cipher)
    _write_private_json(dest_envelope, envelope)
    if _sha256_path(dest_cipher) != envelope["ciphertext_sha256"]:
        raise ExecutiveDRTypedError(
            DRFailureState.UPLOAD_EFFECT_UNKNOWN, "copied artifact digest differs from the source after write"
        )
    return ShipReceipt(
        export_id=str(envelope["export_id"]),
        tag=tag,
        transport="directory",
        duplicate=False,
        ciphertext_sha256=str(envelope["ciphertext_sha256"]),
        byte_size=int(envelope["byte_size"]),
        remote_ref=str(dest_cipher),
    )


def fetch_export_directory(tag: str, *, directory: str | Path, dest_dir: str | Path) -> FetchReceipt:
    store = Path(directory).expanduser()
    object_stem = tag.replace("/", "__")
    source_cipher = store / f"{object_stem}.sqlite3.enc"
    source_envelope = store / f"{object_stem}.envelope.json"
    if not os.path.lexists(source_cipher) or not os.path.lexists(source_envelope):
        raise ExecutiveDRTypedError(DRFailureState.OFFHOST_ABSENT, f"no directory transport object for tag {tag}")

    envelope = _load_envelope(source_envelope)
    _assert_ciphertext_matches_envelope(source_cipher, envelope)
    dest = _ensure_private_directory(Path(dest_dir).expanduser())
    dest_cipher = dest / source_cipher.name
    dest_envelope = dest / source_envelope.name
    _copy_private_file(source_cipher, dest_cipher)
    _write_private_json(dest_envelope, envelope)
    if _sha256_path(dest_cipher) != envelope["ciphertext_sha256"]:
        raise ExecutiveDRTypedError(DRFailureState.LOCAL_CORRUPT, "fetched artifact digest differs from its envelope")

    return FetchReceipt(
        export_id=str(envelope["export_id"]),
        tag=tag,
        transport="directory",
        ciphertext_path=str(dest_cipher),
        envelope_path=str(dest_envelope),
        ciphertext_sha256=str(envelope["ciphertext_sha256"]),
        byte_size=int(envelope["byte_size"]),
        remote_ref=str(source_cipher),
    )


# --------------------------------------------------------------------------
# GitHub-release transport. `_github_request` is the sole HTTP seam so tests
# can stub it and exercise every response path with zero network traffic.
# --------------------------------------------------------------------------


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401 - stdlib signature
        return None


def _github_request(
    method: str,
    url: str,
    *,
    token: str | None = None,
    headers: Mapping[str, str] | None = None,
    data: bytes | None = None,
    timeout: float = 30.0,
) -> tuple[int, dict[str, str], bytes]:
    request_headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "mastermind-executive-dr/1",
    }
    if token:
        request_headers["Authorization"] = f"token {token}"
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, data=data, method=method, headers=request_headers)
    opener = urllib.request.build_opener(_NoRedirectHandler)
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, {str(k): str(v) for k, v in response.headers.items()}, response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read() if exc.fp is not None else b""
        response_headers = {str(k): str(v) for k, v in exc.headers.items()} if exc.headers else {}
        return exc.code, response_headers, body
    except (urllib.error.URLError, OSError, TimeoutError):
        raise ExecutiveDRTypedError(DRFailureState.REMOTE_UNAVAILABLE, "GitHub transport is unreachable") from None


def _github_get_release_by_tag(api_base: str, repo: str, tag: str, token: str) -> dict[str, Any] | None:
    encoded = urllib.parse.quote(tag, safe="")
    status, _headers, body = _github_request("GET", f"{api_base}/repos/{repo}/releases/tags/{encoded}", token=token)
    if status == 200:
        return json.loads(body.decode("utf-8"))
    if status in (401, 403):
        raise ExecutiveDRTypedError(DRFailureState.CREDENTIAL_LOST, "GitHub transport credential was rejected")
    if status != 404:
        raise ExecutiveDRTypedError(DRFailureState.REMOTE_UNAVAILABLE, f"GitHub release lookup failed with status {status}")
    # Adversarial review M10: GitHub's "get a release by tag" endpoint never
    # returns DRAFT releases (documented API behavior) -- the drill lane
    # ships drafts (see `ship_export_github(draft=True)`), so a 404 here does
    # NOT prove absence. Fall back to listing releases and filtering by
    # tag_name, bounded to a handful of pages: drill releases are pruned to
    # the newest 8 under `dr-export/*` by the workflow's retention step, and
    # the bound also protects a busy vault repo from an unbounded scan.
    for page in range(1, 6):
        status, _headers, body = _github_request(
            "GET", f"{api_base}/repos/{repo}/releases?per_page=100&page={page}", token=token
        )
        if status in (401, 403):
            raise ExecutiveDRTypedError(DRFailureState.CREDENTIAL_LOST, "GitHub transport credential was rejected")
        if status != 200:
            raise ExecutiveDRTypedError(DRFailureState.REMOTE_UNAVAILABLE, f"GitHub release listing failed with status {status}")
        releases = json.loads(body.decode("utf-8"))
        if not isinstance(releases, list) or not releases:
            break
        for release in releases:
            if isinstance(release, dict) and release.get("tag_name") == tag:
                return release
        if len(releases) < 100:
            break
    return None


def _github_create_release(api_base: str, repo: str, tag: str, body_text: str, token: str, *, draft: bool = False) -> dict[str, Any]:
    payload = json.dumps(
        {"tag_name": tag, "name": tag, "body": body_text[:_MAX_RELEASE_BODY_BYTES], "draft": draft, "prerelease": False}
    ).encode("utf-8")
    status, _headers, body = _github_request(
        "POST", f"{api_base}/repos/{repo}/releases", token=token, data=payload, headers={"Content-Type": "application/json"}
    )
    if status == 201:
        return json.loads(body.decode("utf-8"))
    if status in (401, 403):
        raise ExecutiveDRTypedError(DRFailureState.CREDENTIAL_LOST, "GitHub transport credential was rejected creating a release")
    if status == 422:
        raise ExecutiveDRTypedError(
            DRFailureState.REMOTE_DIGEST_CONFLICT,
            "GitHub release creation returned 422 (unprocessable) -- either the tag/release already exists, "
            "or the request violated a repository constraint (e.g. an invalid or reserved tag/ref name)",
        )
    raise ExecutiveDRTypedError(DRFailureState.REMOTE_UNAVAILABLE, f"GitHub release creation failed with status {status}")


def _github_upload_asset(upload_url_template: str, path: Path, *, name: str, content_type: str, token: str) -> dict[str, Any]:
    base_url = upload_url_template.split("{", 1)[0]
    upload_url = f"{base_url}?name={urllib.parse.quote(name, safe='')}"
    data = Path(path).read_bytes()
    status, _headers, body = _github_request(
        "POST", upload_url, token=token, data=data, headers={"Content-Type": content_type}
    )
    if status == 201:
        return json.loads(body.decode("utf-8"))
    if status in (401, 403):
        raise ExecutiveDRTypedError(DRFailureState.CREDENTIAL_LOST, "GitHub transport credential was rejected uploading an asset")
    if status == 422:
        raise ExecutiveDRTypedError(DRFailureState.REMOTE_DIGEST_CONFLICT, "GitHub release asset name already exists")
    raise ExecutiveDRTypedError(
        DRFailureState.UPLOAD_EFFECT_UNKNOWN, f"GitHub asset upload returned status {status}; remote effect unknown"
    )


def _github_download_asset(api_base: str, repo: str, asset_id: Any, token: str) -> bytes:
    status, headers, body = _github_request(
        "GET", f"{api_base}/repos/{repo}/releases/assets/{asset_id}", token=token, headers={"Accept": "application/octet-stream"}
    )
    if status in (301, 302, 303, 307, 308):
        location = headers.get("Location") or headers.get("location")
        if not location:
            raise ExecutiveDRTypedError(DRFailureState.REMOTE_UNAVAILABLE, "GitHub asset redirect had no Location header")
        if not location.startswith("https://"):
            raise ExecutiveDRTypedError(
                DRFailureState.REMOTE_UNAVAILABLE, "GitHub asset redirect target is not an https:// URL; refusing to follow it"
            )
        # The redirect target (a signed object-store URL) must never receive
        # our GitHub Authorization header -- second hop is unauthenticated.
        status2, _headers2, body2 = _github_request("GET", location, token=None)
        if status2 != 200:
            raise ExecutiveDRTypedError(DRFailureState.REMOTE_UNAVAILABLE, f"GitHub asset redirect target failed with status {status2}")
        return body2
    if status == 200:
        return body
    if status in (401, 403):
        raise ExecutiveDRTypedError(DRFailureState.CREDENTIAL_LOST, "GitHub transport credential was rejected downloading an asset")
    raise ExecutiveDRTypedError(DRFailureState.REMOTE_UNAVAILABLE, f"GitHub asset download failed with status {status}")


def _resolve_transport_token(*, token: str | None, token_env: str | None) -> str:
    """Exactly one of a literal token (already read from a 0400 file by the
    caller -- see B3) or an env-var name may be supplied."""

    if (token is None) == (token_env is None):
        raise ExecutiveDRTypedError(
            DRFailureState.CREDENTIAL_LOST, "exactly one of a token or a token_env name must be supplied"
        )
    if token is not None:
        if not token:
            raise ExecutiveDRTypedError(DRFailureState.CREDENTIAL_LOST, "transport credential is empty")
        return token
    resolved = os.environ.get(token_env)  # type: ignore[arg-type]
    if not resolved:
        raise ExecutiveDRTypedError(DRFailureState.CREDENTIAL_LOST, f"transport credential env var {token_env} is not set")
    return resolved


def ship_export_github(
    ciphertext_path: str | Path,
    envelope_path: str | Path,
    *,
    repo: str,
    token_env: str | None = None,
    token: str | None = None,
    api_base: str = "https://api.github.com",
    draft: bool = False,
) -> ShipReceipt:
    """Ship to a GitHub release under `_export_tag(envelope)`.

    `draft=True` (the DR-D1 drill lane only -- see `scripts/dr_drill.py`)
    creates the release as a draft: no git tag/ref is created in the
    repository at all until a human publishes it, so a permanent,
    undecryptable-elsewhere tag never accumulates from routine drills. The
    production/vault lane (the nightly backup daemon) always ships
    `draft=False` and is never pruned.
    """

    envelope = _load_envelope(Path(envelope_path))
    _assert_ciphertext_matches_envelope(Path(ciphertext_path), envelope)
    resolved_token = _resolve_transport_token(token=token, token_env=token_env)

    tag = _export_tag(envelope)
    existing = _github_get_release_by_tag(api_base, repo, tag, resolved_token)
    if existing is not None:
        # Adversarial review M1: trusting the release body's declared digest
        # is not proof -- re-download the actual ciphertext asset and hash
        # it before ever reporting a duplicate.
        assets = existing.get("assets") if isinstance(existing.get("assets"), list) else []
        cipher_asset = next((a for a in assets if isinstance(a, dict) and not str(a.get("name", "")).endswith(".envelope.json")), None)
        if cipher_asset is None:
            raise ExecutiveDRTypedError(
                DRFailureState.OFFHOST_ABSENT, f"GitHub release already exists for tag {tag} but has no ciphertext asset"
            )
        downloaded = _github_download_asset(api_base, repo, cipher_asset["id"], resolved_token)
        if hashlib.sha256(downloaded).hexdigest() != envelope["ciphertext_sha256"]:
            raise ExecutiveDRTypedError(
                DRFailureState.REMOTE_DIGEST_CONFLICT, f"GitHub release {tag} ciphertext asset digest does not match this export"
            )
        return ShipReceipt(
            export_id=str(envelope["export_id"]),
            tag=tag,
            transport="github-release",
            duplicate=True,
            ciphertext_sha256=str(envelope["ciphertext_sha256"]),
            byte_size=int(envelope["byte_size"]),
            remote_ref=f"{repo}#{tag}",
        )

    release = _github_create_release(
        api_base, repo, tag, json.dumps(envelope, sort_keys=True, indent=2), resolved_token, draft=draft
    )
    upload_url = release.get("upload_url")
    if not isinstance(upload_url, str) or not upload_url:
        raise ExecutiveDRTypedError(DRFailureState.REMOTE_UNAVAILABLE, "GitHub release creation returned no upload_url")

    cipher_asset = _github_upload_asset(
        upload_url, Path(ciphertext_path), name=Path(ciphertext_path).name, content_type="application/octet-stream", token=resolved_token
    )
    envelope_asset = _github_upload_asset(
        upload_url, Path(envelope_path), name=Path(envelope_path).name, content_type="application/json", token=resolved_token
    )
    asset_id = cipher_asset.get("id")
    envelope_asset_id = envelope_asset.get("id")
    if asset_id is None or envelope_asset_id is None:
        raise ExecutiveDRTypedError(DRFailureState.UPLOAD_EFFECT_UNKNOWN, "GitHub asset upload response had no asset id")

    # Checksum-after-upload (adversarial review M9): re-download BOTH assets
    # and byte-compare before declaring done, not just the ciphertext.
    downloaded_cipher = _github_download_asset(api_base, repo, asset_id, resolved_token)
    if hashlib.sha256(downloaded_cipher).hexdigest() != envelope["ciphertext_sha256"]:
        raise ExecutiveDRTypedError(
            DRFailureState.UPLOAD_EFFECT_UNKNOWN, "uploaded ciphertext asset digest differs from the local file after re-download"
        )
    downloaded_envelope = _github_download_asset(api_base, repo, envelope_asset_id, resolved_token)
    if downloaded_envelope != Path(envelope_path).read_bytes():
        raise ExecutiveDRTypedError(
            DRFailureState.UPLOAD_EFFECT_UNKNOWN, "uploaded envelope asset differs from the local file after re-download"
        )

    return ShipReceipt(
        export_id=str(envelope["export_id"]),
        tag=tag,
        transport="github-release",
        duplicate=False,
        ciphertext_sha256=str(envelope["ciphertext_sha256"]),
        byte_size=int(envelope["byte_size"]),
        remote_ref=f"{repo}#{tag}",
    )


def fetch_export_github(
    tag: str,
    *,
    repo: str,
    dest_dir: str | Path,
    token_env: str | None = None,
    token: str | None = None,
    api_base: str = "https://api.github.com",
) -> FetchReceipt:
    resolved_token = _resolve_transport_token(token=token, token_env=token_env)
    token = resolved_token

    release = _github_get_release_by_tag(api_base, repo, tag, token)
    if release is None:
        raise ExecutiveDRTypedError(DRFailureState.OFFHOST_ABSENT, f"no GitHub release found for tag {tag}")

    assets = release.get("assets")
    if not isinstance(assets, list):
        raise ExecutiveDRTypedError(DRFailureState.RELEASE_SCHEMA_MISMATCH, f"GitHub release {tag} has no assets list")

    envelope_asset = next((item for item in assets if str(item.get("name", "")).endswith(".envelope.json")), None)
    cipher_asset = next((item for item in assets if not str(item.get("name", "")).endswith(".envelope.json")), None)
    if cipher_asset is None:
        raise ExecutiveDRTypedError(DRFailureState.RELEASE_SCHEMA_MISMATCH, f"GitHub release {tag} has no ciphertext asset")

    if envelope_asset is not None:
        envelope_bytes = _github_download_asset(api_base, repo, envelope_asset["id"], token)
    else:
        body_text = release.get("body")
        if not isinstance(body_text, str) or not body_text:
            raise ExecutiveDRTypedError(DRFailureState.RELEASE_SCHEMA_MISMATCH, f"GitHub release {tag} has no envelope asset or body")
        envelope_bytes = body_text.encode("utf-8")

    # Bound the ingress BEFORE anything touches disk (adversarial review
    # minor): `_load_envelope`'s 64 KiB bound only applies to a file already
    # on disk -- check the bytes we are about to write first.
    if len(envelope_bytes) > _MAX_ENVELOPE_BYTES:
        raise ExecutiveDRTypedError(DRFailureState.ENVELOPE_INVALID, f"GitHub release {tag} envelope exceeds the maximum size")

    dest = _ensure_private_directory(Path(dest_dir).expanduser())
    object_stem = tag.replace("/", "__")
    dest_envelope = dest / f"{object_stem}.envelope.json"
    if os.path.lexists(dest_envelope):
        raise ExecutiveDRTypedError(DRFailureState.OUTPUT_CONFLICT, f"fetch destination already has an envelope: {dest_envelope}")
    descriptor = os.open(dest_envelope, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0), 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(envelope_bytes)
            handle.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(dest)
    envelope = _load_envelope(dest_envelope)

    cipher_bytes = _github_download_asset(api_base, repo, cipher_asset["id"], token)
    dest_cipher = dest / f"{object_stem}.sqlite3.enc"
    if os.path.lexists(dest_cipher):
        raise ExecutiveDRTypedError(DRFailureState.OUTPUT_CONFLICT, f"fetch destination already has a ciphertext: {dest_cipher}")
    descriptor = os.open(dest_cipher, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0), 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(cipher_bytes)
            handle.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(dest)

    _assert_ciphertext_matches_envelope(dest_cipher, envelope)

    return FetchReceipt(
        export_id=str(envelope["export_id"]),
        tag=tag,
        transport="github-release",
        ciphertext_path=str(dest_cipher),
        envelope_path=str(dest_envelope),
        ciphertext_sha256=str(envelope["ciphertext_sha256"]),
        byte_size=int(envelope["byte_size"]),
        remote_ref=f"{repo}#{tag}",
    )
