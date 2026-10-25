"""Load a provider credential from an env var or a 0600 file, by name only.

The value is returned to the caller and must not be logged, metered, or placed
on argv. A file pointer that is set but unreadable does not fall back to the
env var.
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Mapping

from control_plane.codex_provider_realm import validate_provider_credential_format

from integrations.hermes_models.contract import ProviderSpec


class CredentialUnavailable(RuntimeError):
    """The named credential pointer is missing or not a private 0600 file."""


_MAX_FILE_BYTES = 8192


def load_credential(spec: ProviderSpec, environ: Mapping[str, str]) -> str:
    """Return the credential for ``spec``.

    When ``credential_file_env`` is present in ``environ``, that path is the
    only source. The file must be a regular, non-symlink file with mode 0600.
    Otherwise ``credential_env`` supplies the value.
    """

    file_pointer = environ.get(spec.credential_file_env)
    if file_pointer is not None and file_pointer != "":
        return _load_file(file_pointer)
    value = environ.get(spec.credential_env, "")
    if not value:
        raise CredentialUnavailable("provider credential is unavailable")
    try:
        return validate_provider_credential_format(value)
    except Exception as exc:
        raise CredentialUnavailable("provider credential is unavailable") from exc


def _load_file(path_text: str) -> str:
    if "\x00" in path_text or "\n" in path_text or "\r" in path_text:
        raise CredentialUnavailable("provider credential is unavailable")
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path_text, flags)
    except OSError as exc:
        raise CredentialUnavailable("provider credential is unavailable") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            raise CredentialUnavailable("provider credential is unavailable")
        if info.st_size > _MAX_FILE_BYTES:
            raise CredentialUnavailable("provider credential is unavailable")
        raw = os.read(fd, _MAX_FILE_BYTES + 1)
    finally:
        os.close(fd)
    if len(raw) > _MAX_FILE_BYTES:
        raise CredentialUnavailable("provider credential is unavailable")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CredentialUnavailable("provider credential is unavailable") from exc
    secret = _parse_secret_text(text)
    try:
        return validate_provider_credential_format(secret)
    except Exception as exc:
        raise CredentialUnavailable("provider credential is unavailable") from exc


def _parse_secret_text(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise CredentialUnavailable("provider credential is unavailable") from exc
        if not isinstance(payload, dict):
            raise CredentialUnavailable("provider credential is unavailable")
        value = payload.get("api_key")
        if not isinstance(value, str):
            raise CredentialUnavailable("provider credential is unavailable")
        return value
    return stripped


def resolve_base_url(spec: ProviderSpec, environ: Mapping[str, str]) -> str:
    """Return the HTTPS base URL. Cursor may override the placeholder by env name."""

    if spec.base_url_env:
        override = environ.get(spec.base_url_env, "").strip()
        if override:
            if not override.startswith("https://") or "@" in override or "api_key=" in override.lower():
                raise CredentialUnavailable("provider credential is unavailable")
            if override.rstrip("/") in {
                "https://ark.ap-southeast.bytepluses.com/api/coding",
                "https://ark.ap-southeast.bytepluses.com/api/coding/v3",
            }:
                raise CredentialUnavailable("provider credential is unavailable")
            return override.rstrip("/")
    return spec.base_url.rstrip("/")
