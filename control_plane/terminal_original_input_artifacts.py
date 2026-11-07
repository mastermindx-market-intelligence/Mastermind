"""Filesystem custody helper for terminal original private input artifacts.

Custody only. Allocates and verifies private original-input files beneath an
already existing, controller-owned runs root. No semantic payload validation,
no lookup by public reference, no dispatch, cleanup, retry, registry, logging
or lifecycle work. The parent Executive Supervisor owns integration,
source-authenticated typed input validation at the command boundary, and
independent risk review.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Final, Optional, Tuple

ARTIFACT_HEADER_SCHEMA: Final[str] = "mastermind.terminal_original_input_artifact.v1"
REFERENCE_SCHEMA: Final[str] = "mastermind.terminal_original_input_reference.v1"
PRIVATE_SUBDIR: Final[str] = "terminal-original-input"
ARTIFACT_FILENAME: Final[str] = "input.bin"
REF_SCHEME: Final[str] = "terminal-input"
MAX_PAYLOAD_BYTES: Final[int] = 256 * 1024
MAX_HEADER_BYTES: Final[int] = 768

TERMINAL_INPUT_INVALID: Final[str] = "TERMINAL_INPUT_INVALID"
TERMINAL_INPUT_CONFLICT: Final[str] = "TERMINAL_INPUT_CONFLICT"
TERMINAL_INPUT_UNAVAILABLE: Final[str] = "TERMINAL_INPUT_UNAVAILABLE"
_CODES: Final[Tuple[str, ...]] = (
    TERMINAL_INPUT_INVALID, TERMINAL_INPUT_CONFLICT, TERMINAL_INPUT_UNAVAILABLE,
)
_COMMAND_RE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_HEX64_RE: Final = re.compile(r"[0-9a-f]{64}")
_HEADER_KEYS: Final = frozenset(
    ("schema", "command_id", "issuer_scope_sha256", "fingerprint_sha256", "payload_sha256")
)
_DIR_MODE: Final = 0o700
_FILE_MODE: Final = 0o600
_O_DIRECTORY: Final = getattr(os, "O_DIRECTORY", 0)
_O_NOFOLLOW: Final = getattr(os, "O_NOFOLLOW", 0)
_O_CLOEXEC: Final = getattr(os, "O_CLOEXEC", 0)
_O_NONBLOCK: Final = getattr(os, "O_NONBLOCK", 0)


class TerminalInputError(Exception):
    """Public custody error. Its string form carries only the stable code."""

    def __init__(self, code: str) -> None:
        self.code = code if code in _CODES else TERMINAL_INPUT_UNAVAILABLE
        super().__init__(self.code)


class _Absent(Exception):
    """Internal: exact artifact path does not exist. Never escapes this module."""


def _fail(code: str) -> TerminalInputError:
    return TerminalInputError(code)


def _current_uid() -> int:
    return os.geteuid()


def _validate_identity(command_id: str, issuer_scope_sha256: str, fingerprint_sha256: str) -> None:
    if not isinstance(command_id, str) or not _COMMAND_RE.fullmatch(command_id):
        raise _fail(TERMINAL_INPUT_INVALID) from None
    for value in (issuer_scope_sha256, fingerprint_sha256):
        if not isinstance(value, str) or not _HEX64_RE.fullmatch(value):
            raise _fail(TERMINAL_INPUT_INVALID) from None


def _stable_key(command_id: str, issuer_scope_sha256: str) -> str:
    """Directory key from command identity only; never payload or fingerprint."""
    digest = hashlib.sha256()
    digest.update(ARTIFACT_HEADER_SCHEMA.encode("ascii"))
    digest.update(b"\x00terminal-input-directory-key\x00")
    digest.update(command_id.encode("ascii"))
    digest.update(b"\x1f")
    digest.update(issuer_scope_sha256.encode("ascii"))
    return digest.hexdigest()


def _header_bytes(command_id: str, issuer_scope_sha256: str, fingerprint_sha256: str,
                  payload_sha256: str) -> bytes:
    header = {
        "schema": ARTIFACT_HEADER_SCHEMA,
        "command_id": command_id,
        "issuer_scope_sha256": issuer_scope_sha256,
        "fingerprint_sha256": fingerprint_sha256,
        "payload_sha256": payload_sha256,
    }
    encoded = json.dumps(header, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    blob = encoded.encode("ascii") + b"\n"
    if len(blob) > MAX_HEADER_BYTES:
        raise _fail(TERMINAL_INPUT_INVALID) from None
    return blob


def _check_dir_stat(st: os.stat_result, *, exact_mode: bool) -> None:
    ok = stat.S_ISDIR(st.st_mode) and st.st_uid == _current_uid() and not st.st_mode & 0o022
    if not ok or (exact_mode and (st.st_mode & 0o7777) != _DIR_MODE):
        raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None


def _check_file_stat(st: os.stat_result) -> None:
    ok = (
        stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_uid == _current_uid()
        and (st.st_mode & 0o7777) == _FILE_MODE
    )
    if not ok:
        raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None


@dataclass(frozen=True)
class TerminalOriginalInputReference:
    """Frozen public receipt. Carries no path, payload or private bytes."""

    schema: str
    input_ref: str
    artifact_sha256: str
    payload_sha256: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "schema": self.schema,
            "input_ref": self.input_ref,
            "artifact_sha256": self.artifact_sha256,
            "payload_sha256": self.payload_sha256,
        }


@dataclass(frozen=True)
class TerminalOriginalInputRecovery:
    """Private owner recovery; never a public receipt or ingress response."""
    reference: TerminalOriginalInputReference
    fingerprint_sha256: str
    payload: bytes = field(repr=False)


class TerminalOriginalInputArtifacts:
    def __init__(self, runs_root: Path) -> None:
        if not _O_DIRECTORY or not _O_NOFOLLOW or not _O_NONBLOCK:
            raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
        root = Path(runs_root)
        if not root.is_absolute() or os.path.realpath(root) != os.path.abspath(root):
            raise _fail(TERMINAL_INPUT_INVALID) from None
        try:
            st = os.stat(root, follow_symlinks=False)
        except OSError:
            raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
        _check_dir_stat(st, exact_mode=False)
        self._runs_root = root
        self._root_identity = (st.st_dev, st.st_ino)

    def _open_root(self) -> int:
        try:
            st = os.stat(self._runs_root, follow_symlinks=False)
        except OSError:
            raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
        _check_dir_stat(st, exact_mode=False)
        if (st.st_dev, st.st_ino) != self._root_identity:
            raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
        fd = None
        try:
            fd = os.open(self._runs_root, os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW | _O_CLOEXEC)
            fst = os.fstat(fd)
            _check_dir_stat(fst, exact_mode=False)
            if (fst.st_dev, fst.st_ino) != self._root_identity:
                raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
        except OSError:
            if fd is not None:
                os.close(fd)
            raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
        except BaseException:
            if fd is not None:
                os.close(fd)
            raise
        return fd

    def _open_child_dir(self, parent_fd: int, name: str, *, create: bool) -> int:
        if create:
            try:
                os.mkdir(name, _DIR_MODE, dir_fd=parent_fd)
            except FileExistsError:
                pass
            except OSError:
                raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
            try:
                os.fsync(parent_fd)
            except OSError:
                raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
        fd = None
        try:
            st = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            _check_dir_stat(st, exact_mode=True)
            fd = os.open(name, os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW | _O_CLOEXEC,
                         dir_fd=parent_fd)
            opened = os.fstat(fd)
            _check_dir_stat(opened, exact_mode=True)
            if (opened.st_dev, opened.st_ino) != (st.st_dev, st.st_ino):
                raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
        except OSError:
            if fd is not None:
                os.close(fd)
            raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
        except BaseException:
            if fd is not None:
                os.close(fd)
            raise
        return fd

    def _open_private_dirs(self, stable_key: str, *, create: bool) -> Tuple[int, int, int]:
        root_fd = self._open_root()
        try:
            private_fd = self._open_child_dir(root_fd, PRIVATE_SUBDIR, create=create)
            try:
                key_fd = self._open_child_dir(private_fd, stable_key, create=create)
            except BaseException:
                os.close(private_fd)
                raise
        except BaseException:
            os.close(root_fd)
            raise
        return root_fd, private_fd, key_fd

    def _verify_bindings(self, stable_key: str, root_fd: int, private_fd: int, key_fd: int) -> None:
        current = os.stat(self._runs_root, follow_symlinks=False)
        opened = os.fstat(root_fd)
        _check_dir_stat(current, exact_mode=False)
        _check_dir_stat(opened, exact_mode=False)
        if ((current.st_dev, current.st_ino) != self._root_identity
                or (opened.st_dev, opened.st_ino) != self._root_identity):
            raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
        for parent, name, child in ((root_fd, PRIVATE_SUBDIR, private_fd),
                                    (private_fd, stable_key, key_fd)):
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            opened = os.fstat(child)
            _check_dir_stat(current, exact_mode=True)
            _check_dir_stat(opened, exact_mode=True)
            if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None

    def _load_file(self, key_fd: int, *, command_id: str, issuer_scope_sha256: str,
                   fingerprint_sha256: str, expected_artifact_sha256: Optional[str] = None,
                   expected_payload_sha256: Optional[str] = None,
                   expected_identity: Optional[Tuple[int, int]] = None,
                   durable: bool = False) -> Tuple[bytes, str]:
        try:
            fd = os.open(ARTIFACT_FILENAME, os.O_RDONLY | _O_NONBLOCK | _O_NOFOLLOW | _O_CLOEXEC,
                         dir_fd=key_fd)
        except FileNotFoundError:
            raise _Absent() from None
        except OSError:
            raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
        try:
            st = os.fstat(fd)
            _check_file_stat(st)
            if not 0 < st.st_size <= MAX_HEADER_BYTES + MAX_PAYLOAD_BYTES:
                raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
            if expected_identity is not None and (st.st_dev, st.st_ino) != expected_identity:
                raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
            header_blob = self._read_header(fd)
            header = self._parse_header(header_blob)
            expected = {
                "schema": ARTIFACT_HEADER_SCHEMA,
                "command_id": command_id,
                "issuer_scope_sha256": issuer_scope_sha256,
                "fingerprint_sha256": fingerprint_sha256,
            }
            if expected_payload_sha256 is not None:
                expected["payload_sha256"] = expected_payload_sha256
            if any(header[k] != v for k, v in expected.items()):
                raise _fail(TERMINAL_INPUT_CONFLICT) from None
            payload = bytearray()
            while len(payload) <= MAX_PAYLOAD_BYTES:
                chunk = os.read(fd, min(65536, MAX_PAYLOAD_BYTES + 1 - len(payload)))
                if not chunk:
                    break
                payload.extend(chunk)
            final = os.fstat(fd)
            if (final.st_dev, final.st_ino) != (st.st_dev, st.st_ino):
                raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
            _check_file_stat(final)
            linked = os.stat(ARTIFACT_FILENAME, dir_fd=key_fd, follow_symlinks=False)
            _check_file_stat(linked)
            if (linked.st_dev, linked.st_ino) != (st.st_dev, st.st_ino):
                raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
            size_ok = final.st_size == len(header_blob) + len(payload)
            if not size_ok or not payload or len(payload) > MAX_PAYLOAD_BYTES:
                raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
            payload_bytes = bytes(payload)
            if hashlib.sha256(payload_bytes).hexdigest() != header["payload_sha256"]:
                raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
            artifact_sha256 = hashlib.sha256(header_blob + payload_bytes).hexdigest()
            if expected_artifact_sha256 is not None and artifact_sha256 != expected_artifact_sha256:
                raise _fail(TERMINAL_INPUT_CONFLICT) from None
            if durable:
                os.fsync(fd)
            return payload_bytes, artifact_sha256
        finally:
            os.close(fd)

    def _read_header(self, fd: int) -> bytes:
        buf = bytearray()
        while len(buf) <= MAX_HEADER_BYTES:
            chunk = os.read(fd, 4096)
            if not chunk:
                break
            buf.extend(chunk)
            if b"\n" in buf:
                break
        nl = buf.find(b"\n")
        if nl < 0 or nl + 1 > MAX_HEADER_BYTES:
            raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
        header_blob = bytes(buf[: nl + 1])
        os.lseek(fd, len(header_blob), os.SEEK_SET)
        return header_blob

    def _parse_header(self, header_blob: bytes) -> Dict[str, str]:
        try:
            header = json.loads(header_blob.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
        keys_ok = isinstance(header, dict) and set(header) == set(_HEADER_KEYS)
        if not keys_ok or not all(isinstance(v, str) for v in header.values()):
            raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
        canonical = _header_bytes(header["command_id"], header["issuer_scope_sha256"],
                                  header["fingerprint_sha256"], header["payload_sha256"])
        if header_blob != canonical:
            raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
        return header

    def prepare(self, *, command_id: str, issuer_scope_sha256: str, fingerprint_sha256: str,
                payload: bytes) -> TerminalOriginalInputReference:
        try:
            return self._prepare(command_id=command_id, issuer_scope_sha256=issuer_scope_sha256,
                                 fingerprint_sha256=fingerprint_sha256, payload=payload)
        except TerminalInputError:
            raise
        except Exception:
            raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None

    def _prepare(self, *, command_id: str, issuer_scope_sha256: str, fingerprint_sha256: str,
                 payload: bytes) -> TerminalOriginalInputReference:
        _validate_identity(command_id, issuer_scope_sha256, fingerprint_sha256)
        if not isinstance(payload, bytes) or not payload or len(payload) > MAX_PAYLOAD_BYTES:
            raise _fail(TERMINAL_INPUT_INVALID) from None
        payload_sha256 = hashlib.sha256(payload).hexdigest()
        stable_key = _stable_key(command_id, issuer_scope_sha256)
        header = _header_bytes(command_id, issuer_scope_sha256, fingerprint_sha256, payload_sha256)
        identity = {
            "command_id": command_id,
            "issuer_scope_sha256": issuer_scope_sha256,
            "fingerprint_sha256": fingerprint_sha256,
        }
        root_fd, private_fd, key_fd = self._open_private_dirs(stable_key, create=True)
        try:
            try:
                _, artifact_sha256 = self._reconcile(key_fd, payload_sha256, identity)
            except _Absent:
                _, artifact_sha256 = self._create_and_verify(
                    key_fd, header, payload, payload_sha256, identity
                )
            os.fsync(key_fd)
            self._verify_bindings(stable_key, root_fd, private_fd, key_fd)
        finally:
            os.close(key_fd)
            os.close(private_fd)
            os.close(root_fd)
        return TerminalOriginalInputReference(
            schema=REFERENCE_SCHEMA,
            input_ref=f"{REF_SCHEME}:{stable_key}",
            artifact_sha256=artifact_sha256,
            payload_sha256=payload_sha256,
        )

    def _reconcile(self, key_fd: int, payload_sha256: str, identity: Dict[str, str]) -> Tuple[bytes, str]:
        return self._load_file(key_fd, expected_payload_sha256=payload_sha256, durable=True, **identity)

    def _create_and_verify(self, key_fd: int, header: bytes, payload: bytes,
                           payload_sha256: str, identity: Dict[str, str]) -> Tuple[bytes, str]:
        try:
            fd = os.open(ARTIFACT_FILENAME,
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW | _O_CLOEXEC,
                         _FILE_MODE, dir_fd=key_fd)
        except FileExistsError:
            try:
                return self._reconcile(key_fd, payload_sha256, identity)
            except _Absent:
                raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
        except OSError:
            raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
        try:
            view = memoryview(header + payload)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("private input write made no progress")
                view = view[written:]
            os.fsync(fd)
            created = (os.fstat(fd).st_dev, os.fstat(fd).st_ino)
        except OSError:
            raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
        finally:
            os.close(fd)
        try:
            os.fsync(key_fd)
        except OSError:
            raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None
        return self._load_file(key_fd, expected_payload_sha256=payload_sha256,
                               expected_identity=created, **identity)

    def lookup_original(self, *, command_id: str, issuer_scope_sha256: str):
        """Read ONLY one original command/issuer key after a lost prepare return.

        No ref/path lookup, listing, creation, rewrite or authority is provided.
        The caller must qualify its actual issuer scope and complete the
        incumbent idempotent prepare before committing recovered custody.
        """
        try:
            _validate_identity(command_id, issuer_scope_sha256, "0" * 64)
            stable_key = _stable_key(command_id, issuer_scope_sha256)
            opened = []
            root_fd = self._open_root(); opened.append(root_fd)
            try:
                parent = root_fd
                for name in (PRIVATE_SUBDIR, stable_key):
                    try:
                        os.stat(name, dir_fd=parent, follow_symlinks=False)
                    except FileNotFoundError:
                        return None  # absence is not a no-effect receipt
                    descriptor = self._open_child_dir(parent, name, create=False)
                    opened.append(descriptor); parent = descriptor
                private_fd, key_fd = opened[1:]
                try:
                    fd = os.open(ARTIFACT_FILENAME, os.O_RDONLY | _O_NONBLOCK | _O_NOFOLLOW | _O_CLOEXEC,
                                 dir_fd=key_fd)
                except FileNotFoundError:
                    self._verify_bindings(stable_key, root_fd, private_fd, key_fd)
                    return None
                try:
                    st = os.fstat(fd); _check_file_stat(st)
                    if not 0 < st.st_size <= MAX_HEADER_BYTES + MAX_PAYLOAD_BYTES:
                        raise _fail(TERMINAL_INPUT_UNAVAILABLE)
                    header = self._parse_header(self._read_header(fd))
                    _validate_identity(header["command_id"], header["issuer_scope_sha256"], header["fingerprint_sha256"])
                    if (header["command_id"] != command_id or header["issuer_scope_sha256"] != issuer_scope_sha256
                            or _HEX64_RE.fullmatch(header["payload_sha256"]) is None):
                        raise _fail(TERMINAL_INPUT_CONFLICT)
                    identity = (st.st_dev, st.st_ino)
                finally:
                    os.close(fd)
                payload, artifact_sha = self._load_file(key_fd, command_id=command_id,
                    issuer_scope_sha256=issuer_scope_sha256, fingerprint_sha256=header["fingerprint_sha256"],
                    expected_identity=identity)
                self._verify_bindings(stable_key, root_fd, private_fd, key_fd)
                ref = TerminalOriginalInputReference(schema=REFERENCE_SCHEMA, input_ref=REF_SCHEME + ":" + stable_key,
                    artifact_sha256=artifact_sha, payload_sha256=hashlib.sha256(payload).hexdigest())
                return TerminalOriginalInputRecovery(ref, header["fingerprint_sha256"], payload)
            finally:
                for descriptor in reversed(opened): os.close(descriptor)
        except TerminalInputError:
            raise
        except Exception:
            raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None

    def read(self, *, command_id: str, issuer_scope_sha256: str, fingerprint_sha256: str,
             expected_artifact_sha256: str) -> bytes:
        try:
            return self._read(command_id=command_id, issuer_scope_sha256=issuer_scope_sha256,
                              fingerprint_sha256=fingerprint_sha256,
                              expected_artifact_sha256=expected_artifact_sha256)
        except TerminalInputError:
            raise
        except Exception:
            raise _fail(TERMINAL_INPUT_UNAVAILABLE) from None

    def _read(self, *, command_id: str, issuer_scope_sha256: str, fingerprint_sha256: str,
              expected_artifact_sha256: str) -> bytes:
        _validate_identity(command_id, issuer_scope_sha256, fingerprint_sha256)
        if not isinstance(expected_artifact_sha256, str) or not _HEX64_RE.fullmatch(
            expected_artifact_sha256
        ):
            raise _fail(TERMINAL_INPUT_INVALID) from None
        stable_key = _stable_key(command_id, issuer_scope_sha256)
        root_fd, private_fd, key_fd = self._open_private_dirs(stable_key, create=False)
        try:
            payload, _ = self._load_file(
                key_fd,
                command_id=command_id,
                issuer_scope_sha256=issuer_scope_sha256,
                fingerprint_sha256=fingerprint_sha256,
                expected_artifact_sha256=expected_artifact_sha256,
            )
            self._verify_bindings(stable_key, root_fd, private_fd, key_fd)
        finally:
            os.close(key_fd)
            os.close(private_fd)
            os.close(root_fd)
        return payload
