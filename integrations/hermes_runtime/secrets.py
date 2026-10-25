"""Read the operator secrets file. Values never belong in a unit, log, or receipt."""
from __future__ import annotations

import os
from pathlib import Path
import re
import stat
from types import MappingProxyType

from .constants import (
    DASHBOARD_PASSWORD_ENV,
    DASHBOARD_USERNAME_ENV,
    DEFAULT_CHILD_SECRET_ENV,
    GATEWAY_TOKEN_ENV,
)
from .errors import RuntimeRefusal

_KEY = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_PLACEHOLDERS = frozenset({
    "changeme", "password", "secret", "token", "hermes", "replace-me",
})
_CHILD_SECRET_ENV = set(DEFAULT_CHILD_SECRET_ENV)


def register_child_secret_env(names: set[str] | frozenset[str] | list[str]) -> None:
    """WP2 (and only an in-process sibling) may name extra env keys to forward.

    Registration does not read the secrets file and does not grant a provider.
    Unknown keys in the file stay unforwarded until a sibling names them.
    """
    for name in names:
        if not isinstance(name, str) or not _KEY.fullmatch(name):
            raise RuntimeRefusal("INVALID_SECRET_ENV_NAME")
        if name == GATEWAY_TOKEN_ENV:
            raise RuntimeRefusal("GATEWAY_TOKEN_STAYS_ON_THE_FRONT_DOOR")
        _CHILD_SECRET_ENV.add(name)


def clear_child_secret_env() -> None:
    _CHILD_SECRET_ENV.clear()
    _CHILD_SECRET_ENV.update(DEFAULT_CHILD_SECRET_ENV)


def child_secret_env_names() -> frozenset[str]:
    return frozenset(_CHILD_SECRET_ENV)


class Secrets:
    __slots__ = ("token", "dashboard_username", "dashboard_password", "values")

    def __init__(self, token: str, username: str, password: str, values: dict[str, str]):
        self.token = token
        self.dashboard_username = username
        self.dashboard_password = password
        self.values = MappingProxyType(values)

    def __repr__(self) -> str:
        return "Secrets(redacted)"


def load_secrets(path: Path) -> Secrets:
    if not isinstance(path, Path):
        path = Path(path)
    if path.is_symlink():
        raise RuntimeRefusal("SECRETS_SYMLINK_REFUSED")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        if exc.errno in {getattr(os, "ELOOP", 40), getattr(os, "EMLINK", 31)}:
            raise RuntimeRefusal("SECRETS_SYMLINK_REFUSED") from None
        raise RuntimeRefusal("SECRETS_FILE_MISSING") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeRefusal("SECRETS_FILE_NOT_REGULAR")
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise RuntimeRefusal("SECRETS_MODE_NOT_0600")
        if info.st_uid != os.geteuid():
            raise RuntimeRefusal("SECRETS_NOT_OWNED_BY_RUNTIME_USER")
        if info.st_size > 64 * 1024:
            raise RuntimeRefusal("SECRETS_FILE_TOO_LARGE")
        raw = os.read(fd, info.st_size + 1)
    finally:
        os.close(fd)
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeError:
        raise RuntimeRefusal("SECRETS_FILE_NOT_UTF8") from None
    values = _parse(text)
    token = values.get(GATEWAY_TOKEN_ENV, "")
    _validate_token(token)
    username = values.get(DASHBOARD_USERNAME_ENV, "hermes")
    password = values.get(DASHBOARD_PASSWORD_ENV, token)
    if not _KEY.fullmatch(username) and not re.fullmatch(r"[a-z][a-z0-9._-]{0,63}", username):
        raise RuntimeRefusal("DASHBOARD_USERNAME_INVALID")
    _validate_token(password)
    return Secrets(token, username, password, values)


def _validate_token(token: str) -> None:
    if not isinstance(token, str) or len(token) < 16 or any(ch.isspace() for ch in token):
        raise RuntimeRefusal("SECRETS_TOKEN_UNUSABLE")
    if token.lower() in _PLACEHOLDERS:
        raise RuntimeRefusal("SECRETS_TOKEN_PLACEHOLDER")


def _parse(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" not in line:
            raise RuntimeRefusal("SECRETS_LINE_INVALID")
        key, value = line.split("=", 1)
        key = key.strip()
        if not _KEY.fullmatch(key):
            raise RuntimeRefusal("SECRETS_LINE_INVALID")
        if key in values:
            raise RuntimeRefusal("SECRETS_DUPLICATE_KEY")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if "\x00" in value:
            raise RuntimeRefusal("SECRETS_LINE_INVALID")
        values[key] = value
    if GATEWAY_TOKEN_ENV not in values:
        raise RuntimeRefusal("SECRETS_TOKEN_MISSING")
    return values


def child_env(secrets: Secrets, *, home: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for the Hermes child. Parent credentials are not copied."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "HERMES_HOME": str(home),
        "LANG": "C.UTF-8",
        DASHBOARD_USERNAME_ENV: secrets.dashboard_username,
        DASHBOARD_PASSWORD_ENV: secrets.dashboard_password,
    }
    for name in sorted(_CHILD_SECRET_ENV):
        if name in env or name == GATEWAY_TOKEN_ENV:
            continue
        if name in secrets.values:
            env[name] = secrets.values[name]
    for key, value in (extra or {}).items():
        if not isinstance(key, str) or not key.startswith("HERMES_STUB_"):
            raise RuntimeRefusal("EXTRA_CHILD_ENV_REFUSED")
        if "\n" in value or "\x00" in value:
            raise RuntimeRefusal("EXTRA_CHILD_ENV_REFUSED")
        env[key] = value
    return env
