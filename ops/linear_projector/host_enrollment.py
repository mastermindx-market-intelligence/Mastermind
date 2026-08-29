"""Fixed, production-disarmed credential boundary for the Linear projector.

This Task-1 slice owns only compile-time coordinates, opaque CLI parsing and
secret-surface refusal. It performs no filesystem mutation, secret input,
network access, OAuth exchange, Linear mutation or service control.
"""
from __future__ import annotations

import argparse
import re
from collections.abc import Mapping, Sequence
from pathlib import Path


ROOT = Path("/Library/Application Support/MastermindPortfolioProjector")
CONFIG_DIR = ROOT / "config"
CONFIG_PATH = CONFIG_DIR / "projector.json"
SECRET_PATH = CONFIG_DIR / "oauth-client-secret"

WORKSPACE_ID = "93bfb3d6-93f1-48a8-9720-aa653cba4335"
TEAM_ID = "26b5bb87-2482-4f8f-a42f-955250bd9eaf"
TEAM_KEY = "MAS"
APP_NAME = "Mastermind Portfolio Projector"
CONFIG_SCHEMA = "mastermind.linear_projector_host.v1"

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


__all__ = [
    "APP_NAME",
    "CONFIG_DIR",
    "CONFIG_PATH",
    "CONFIG_SCHEMA",
    "ERROR_CODES",
    "ProjectorHostError",
    "ROOT",
    "SECRET_ENV_KEYS",
    "SECRET_PATH",
    "TEAM_ID",
    "TEAM_KEY",
    "WORKSPACE_ID",
    "assert_secret_surfaces_clean",
    "build_parser",
]
