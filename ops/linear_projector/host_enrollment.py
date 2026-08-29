"""Fixed, production-disarmed credential boundary for the Linear projector.

The current slice owns fixed host coordinates, opaque parsing/secret input,
safe directory preparation and create-once credential files. It performs no
network access, OAuth exchange, Linear mutation or service control.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import termios
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import BinaryIO


ROOT = Path("/Library/Application Support/MastermindPortfolioProjector")
CONFIG_DIR = ROOT / "config"
CONFIG_PATH = CONFIG_DIR / "projector.json"
SECRET_PATH = CONFIG_DIR / "oauth-client-secret"

WORKSPACE_ID = "93bfb3d6-93f1-48a8-9720-aa653cba4335"
TEAM_ID = "26b5bb87-2482-4f8f-a42f-955250bd9eaf"
TEAM_KEY = "MAS"
APP_NAME = "Mastermind Portfolio Projector"
CONFIG_SCHEMA = "mastermind.linear_projector_host.v1"
MAX_SECRET_BYTES = 4096
MAX_CLIENT_ID_CHARS = 256
MAX_PRIVATE_FILE_BYTES = 64 * 1024

ERROR_CODES = frozenset(
    {
        "PROJECTOR_HOST_ARGUMENTS_REFUSED",
        "PROJECTOR_HOST_SECRET_SURFACE_REFUSED",
        "PROJECTOR_HOST_PREPARE_REFUSED",
        "PROJECTOR_HOST_INPUT_REFUSED",
        "PROJECTOR_HOST_COLLISION",
        "PROJECTOR_HOST_WRITE_REFUSED",
        "PROJECTOR_HOST_CONFIG_REFUSED",
        "PROJECTOR_HOST_PERMISSIONS_REFUSED",
        "PROJECTOR_HOST_CLIENT_ID_MISMATCH",
        "PROJECTOR_HOST_INTERNAL",
    }
)

SECRET_ENV_KEYS = frozenset(
    {
        "LINEAR_CLIENT_SECRET",
        "LINEAR_ACCESS_TOKEN",
        "LINEAR_API_KEY",
        "MASTERMIND_LINEAR_CLIENT_SECRET",
        "MASTERMIND_LINEAR_ACCESS_TOKEN",
    }
)

_LINEAR_API_SECRET_RE = re.compile(r"(?i)lin_api_[A-Za-z0-9._-]{4,}")
_BEARER_SECRET_RE = re.compile(r"(?i)(?:^|\s)bearer\s+[^\s]{4,}")
_OAUTH_SECRET_RE = re.compile(
    r"(?i)(?:client[_-]?secret|access[_-]?token|refresh[_-]?token|"
    r"oauth[_-]?(?:secret|token))[=:][^\s]{4,}"
)


class ProjectorHostError(RuntimeError):
    """One opaque closed refusal code for the projector host boundary."""

    def __init__(self, code: str) -> None:
        if code not in ERROR_CODES:
            raise ValueError("unknown projector host error code")
        super().__init__(code)
        self.code = code


class _OpaqueParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # pragma: no cover - argparse path
        raise ProjectorHostError("PROJECTOR_HOST_ARGUMENTS_REFUSED")


def build_parser() -> argparse.ArgumentParser:
    """Expose only the three fixed CRED0 administrator commands."""

    parser = _OpaqueParser(description="Mastermind Linear projector host boundary")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare")

    enroll = commands.add_parser("enroll")
    enroll.add_argument("--client-id", required=True)

    verify = commands.add_parser("verify")
    verify.add_argument("--expected-client-id", required=True)
    return parser


def _looks_secret_shaped(value: object) -> bool:
    text = str(value)
    return any(
        pattern.search(text) is not None
        for pattern in (_LINEAR_API_SECRET_RE, _BEARER_SECRET_RE, _OAUTH_SECRET_RE)
    )


def assert_secret_surfaces_clean(
    *, argv: Sequence[str], environ: Mapping[str, str]
) -> None:
    """Refuse obvious secret material before any command behavior occurs."""

    if any(_looks_secret_shaped(value) for value in argv):
        raise ProjectorHostError("PROJECTOR_HOST_SECRET_SURFACE_REFUSED")

    for key, value in environ.items():
        if str(key).upper() in SECRET_ENV_KEYS or _looks_secret_shaped(value):
            raise ProjectorHostError("PROJECTOR_HOST_SECRET_SURFACE_REFUSED")


def _decode_secret_bytes(raw: bytes) -> bytes:
    """Validate one bounded ASCII secret line and retain it only as bytes."""

    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_SECRET_BYTES + 1:
        raise ProjectorHostError("PROJECTOR_HOST_INPUT_REFUSED")
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    if (
        not raw
        or len(raw) > MAX_SECRET_BYTES
        or b"\n" in raw
        or b"\r" in raw
        or any(byte <= 32 or byte == 127 or byte >= 128 for byte in raw)
    ):
        raise ProjectorHostError("PROJECTOR_HOST_INPUT_REFUSED")
    return raw


def _tty_fd(stream: BinaryIO) -> int | None:
    try:
        descriptor = stream.fileno()
    except (AttributeError, OSError, ValueError):
        return None
    return descriptor if os.isatty(descriptor) else None


def read_secret_from_stdin(stream: BinaryIO) -> bytes:
    """Read exactly one bounded line, muting terminal echo when native."""

    descriptor = _tty_fd(stream)
    if descriptor is None:
        return _decode_secret_bytes(stream.readline(MAX_SECRET_BYTES + 2))

    try:
        original = termios.tcgetattr(descriptor)
        muted = list(original)
        muted[3] &= ~termios.ECHO
        termios.tcsetattr(descriptor, termios.TCSANOW, muted)
    except (OSError, termios.error):
        raise ProjectorHostError("PROJECTOR_HOST_INPUT_REFUSED") from None

    try:
        raw = stream.readline(MAX_SECRET_BYTES + 2)
    finally:
        try:
            termios.tcsetattr(descriptor, termios.TCSANOW, original)
        except (OSError, termios.error):
            raise ProjectorHostError("PROJECTOR_HOST_INPUT_REFUSED") from None
    return _decode_secret_bytes(raw)


def _assert_safe_directory(
    path: Path, *, uid: int, gid: int, mode: int
) -> None:
    """Require one real directory with exact owner/group/mode metadata."""

    try:
        info = Path(path).lstat()
    except OSError:
        raise ProjectorHostError("PROJECTOR_HOST_PERMISSIONS_REFUSED") from None
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != int(uid)
        or info.st_gid != int(gid)
        or stat.S_IMODE(info.st_mode) != int(mode)
    ):
        raise ProjectorHostError("PROJECTOR_HOST_PERMISSIONS_REFUSED")


def _prepare_directory(path: Path, *, uid: int, gid: int, mode: int) -> None:
    path = Path(path)
    created = False
    try:
        path.mkdir(mode=mode)
        created = True
    except FileExistsError:
        pass
    except OSError:
        raise ProjectorHostError("PROJECTOR_HOST_PREPARE_REFUSED") from None

    if created:
        try:
            path.chmod(mode)
        except OSError:
            raise ProjectorHostError("PROJECTOR_HOST_PREPARE_REFUSED") from None
    _assert_safe_directory(path, uid=uid, gid=gid, mode=mode)


def prepare_host(
    *, root: Path = ROOT, uid: int = 0, gid: int = 0
) -> None:
    """Create/check only the fixed root and config directory boundary."""

    root = Path(root)
    if not root.is_absolute():
        raise ProjectorHostError("PROJECTOR_HOST_PREPARE_REFUSED")
    _prepare_directory(root, uid=uid, gid=gid, mode=0o750)
    _prepare_directory(root / "config", uid=uid, gid=gid, mode=0o750)


def _validate_client_id(client_id: object) -> str:
    if (
        not isinstance(client_id, str)
        or not 1 <= len(client_id) <= MAX_CLIENT_ID_CHARS
        or client_id.strip() != client_id
        or any(ord(character) < 33 or ord(character) > 126 for character in client_id)
    ):
        raise ProjectorHostError("PROJECTOR_HOST_CONFIG_REFUSED")
    return client_id


def build_config_document(*, client_id: str) -> dict[str, str]:
    """Build the exact non-secret projector identity document."""

    return {
        "schema": CONFIG_SCHEMA,
        "app_name": APP_NAME,
        "client_id": _validate_client_id(client_id),
        "workspace_id": WORKSPACE_ID,
        "team_id": TEAM_ID,
        "team_key": TEAM_KEY,
    }


def _fsync_parent(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path.parent, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_new_private_file(
    path: Path,
    payload: bytes,
    *,
    uid: int,
    gid: int,
    mode: int,
) -> None:
    """Create one final private file exactly once and fsync its parent."""

    path = Path(path)
    if (
        not path.is_absolute()
        or not isinstance(payload, bytes)
        or not payload
        or len(payload) > MAX_PRIVATE_FILE_BYTES
    ):
        raise ProjectorHostError("PROJECTOR_HOST_WRITE_REFUSED")
    try:
        parent = path.parent.lstat()
    except OSError:
        raise ProjectorHostError("PROJECTOR_HOST_WRITE_REFUSED") from None
    if stat.S_ISLNK(parent.st_mode) or not stat.S_ISDIR(parent.st_mode):
        raise ProjectorHostError("PROJECTOR_HOST_WRITE_REFUSED")

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        raise ProjectorHostError("PROJECTOR_HOST_COLLISION") from None
    except OSError:
        raise ProjectorHostError("PROJECTOR_HOST_WRITE_REFUSED") from None

    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ProjectorHostError("PROJECTOR_HOST_WRITE_REFUSED")
        if info.st_uid != int(uid) or info.st_gid != int(gid):
            os.fchown(descriptor, int(uid), int(gid))
        os.fchmod(descriptor, int(mode))
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise ProjectorHostError("PROJECTOR_HOST_WRITE_REFUSED")
            view = view[written:]
        os.fsync(descriptor)
    except ProjectorHostError:
        raise
    except OSError:
        raise ProjectorHostError("PROJECTOR_HOST_WRITE_REFUSED") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    try:
        final = path.lstat()
    except OSError:
        raise ProjectorHostError("PROJECTOR_HOST_WRITE_REFUSED") from None
    if (
        stat.S_ISLNK(final.st_mode)
        or not stat.S_ISREG(final.st_mode)
        or final.st_nlink != 1
        or final.st_uid != int(uid)
        or final.st_gid != int(gid)
        or stat.S_IMODE(final.st_mode) != int(mode)
    ):
        raise ProjectorHostError("PROJECTOR_HOST_WRITE_REFUSED")
    try:
        _fsync_parent(path)
    except OSError:
        raise ProjectorHostError("PROJECTOR_HOST_WRITE_REFUSED") from None


def _require_final_paths_absent(config_path: Path, secret_path: Path) -> None:
    for path in (config_path, secret_path):
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            raise ProjectorHostError("PROJECTOR_HOST_COLLISION") from None
        raise ProjectorHostError("PROJECTOR_HOST_COLLISION")


def enroll(
    *,
    client_id: str,
    secret: bytes,
    root: Path = ROOT,
    uid: int = 0,
    gid: int = 0,
) -> None:
    """Create exact config + secret files once inside an already-prepared root."""

    root = Path(root)
    if not root.is_absolute():
        raise ProjectorHostError("PROJECTOR_HOST_CONFIG_REFUSED")
    config_dir = root / "config"
    _assert_safe_directory(root, uid=uid, gid=gid, mode=0o750)
    _assert_safe_directory(config_dir, uid=uid, gid=gid, mode=0o750)

    document = build_config_document(client_id=client_id)
    secret = _decode_secret_bytes(secret)
    config_payload = (
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
        + b"\n"
    )
    config_path = config_dir / "projector.json"
    secret_path = config_dir / "oauth-client-secret"
    _require_final_paths_absent(config_path, secret_path)

    write_new_private_file(
        config_path,
        config_payload,
        uid=uid,
        gid=gid,
        mode=0o640,
    )
    write_new_private_file(
        secret_path,
        secret,
        uid=uid,
        gid=gid,
        mode=0o600,
    )


__all__ = [
    "APP_NAME",
    "CONFIG_DIR",
    "CONFIG_PATH",
    "CONFIG_SCHEMA",
    "ERROR_CODES",
    "MAX_CLIENT_ID_CHARS",
    "MAX_SECRET_BYTES",
    "ProjectorHostError",
    "ROOT",
    "SECRET_ENV_KEYS",
    "SECRET_PATH",
    "TEAM_ID",
    "TEAM_KEY",
    "WORKSPACE_ID",
    "assert_secret_surfaces_clean",
    "build_config_document",
    "build_parser",
    "enroll",
    "prepare_host",
    "read_secret_from_stdin",
    "write_new_private_file",
]
