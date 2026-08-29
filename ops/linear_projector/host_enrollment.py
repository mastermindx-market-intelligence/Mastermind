"""Fixed, production-disarmed credential boundary for the Linear projector.

The current slice owns fixed host coordinates, opaque parsing/secret input, and
safe preparation of the projector-specific directory boundary. It performs no
credential-file write, network access, OAuth exchange, Linear mutation or
service control.
"""
from __future__ import annotations

import argparse
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


__all__ = [
    "APP_NAME",
    "CONFIG_DIR",
    "CONFIG_PATH",
    "CONFIG_SCHEMA",
    "ERROR_CODES",
    "MAX_SECRET_BYTES",
    "ProjectorHostError",
    "ROOT",
    "SECRET_ENV_KEYS",
    "SECRET_PATH",
    "TEAM_ID",
    "TEAM_KEY",
    "WORKSPACE_ID",
    "assert_secret_surfaces_clean",
    "build_parser",
    "prepare_host",
    "read_secret_from_stdin",
]
