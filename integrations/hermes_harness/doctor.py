"""Report credentials, ids, and host grants that are still absent.

The report names pointers. It does not print secret values, file bodies, or
exception text from a credential parser.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from collections.abc import Mapping
from pathlib import Path

from integrations.hermes_models.contract import PROFILE_PRIMARY, PROVIDERS, provider, native_provider
from integrations.hermes_models.credentials import CredentialUnavailable, load_credential
from integrations.hermes_runtime.constants import PINNED_UPSTREAM_SHA
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.secrets import load_secrets

SCHEMA = "mastermind.hermes_harness.doctor.v1"
# Primary native model keys originate in the role-private secrets file.
_NATIVE_PRIMARY_ROLE_BY_ENV = {
    provider(ident).credential_env: role for role, ident in PROFILE_PRIMARY.items()
}
M2STUDIO_MACHINE = "61f4e9d7-b202-4cda-85ed-36904689931e"

_CREDENTIALS = (
    ("BYTEPLUS_MODELARK_API_KEY", "BYTEPLUS_MODELARK_API_KEY_FILE"),
    ("CURSOR_API_KEY", "CURSOR_API_KEY_FILE"),
    ("MASTERMIND_STEWARD_ACCESS_TOKEN", "MASTERMIND_STEWARD_ACCESS_TOKEN_FILE"),
    ("MINIMAX_TOKEN_PLAN_KEY", "MINIMAX_TOKEN_PLAN_KEY_FILE"),
    ("ZAI_API_KEY", "ZAI_API_KEY_FILE"),
)
_ENDPOINTS = (
    "HERMES_CURSOR_POOL_BASE_URL",
    "MASTERMIND_STEWARD_MCP_URL",
)
_SECRET_FILES = (
    "mmmeta.secrets.env",
    "mmsecretary.secrets.env",
)
_ALWAYS_MISSING_GRANTS = (
    "grant:executive_admission",
    "grant:fabric_live_submit",
    "grant:m2studio_computer_use",
    "grant:mac_tcc",
)


def doctor(
    *,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    systemd_user: bool | None = None,
    upstream_attested: bool | None = None,
    roster_path: Path | None = None,
) -> dict:
    env = dict(os.environ if environ is None else environ)
    root = Path.home() if home is None else home
    missing: list[str] = []
    for env_name, file_name in _CREDENTIALS:
        native_role = _NATIVE_PRIMARY_ROLE_BY_ENV.get(env_name)
        # A shell key can qualify an offline model test, but never a native
        # systemd child. Report its actual receiving credential source here.
        present = (
            _native_primary_present(root, native_role)
            if native_role is not None
            else _credential_present(env, env_name, file_name)
        )
        if not present:
            missing.append(f"credential:{env_name}")
    for name in _SECRET_FILES:
        path = root / ".config" / "hermes-runtime" / name
        if not _gateway_file_ok(path):
            missing.append(f"credential_file:{name}")
    for name in _ENDPOINTS:
        if not env.get(name, "").strip():
            missing.append(f"endpoint:{name}")
    missing.extend(_ALWAYS_MISSING_GRANTS)
    attested = _upstream_attested(root) if upstream_attested is None else upstream_attested
    if not attested:
        missing.append("grant:pinned_upstream_checkout")
    manager = _systemd_user_manager() if systemd_user is None else systemd_user
    if not manager:
        missing.append("grant:ubuntu1_systemd_user_manager")
    missing.extend(_agent_identity_gaps(root, roster_path=roster_path))
    missing.append("id:DOT_BOT_USER_IDS")
    missing = sorted(set(missing))
    return {
        "schema": SCHEMA,
        "status": "MISSING" if missing else "READY",
        "missing": missing,
        "missing_count": len(missing),
        "m2studio_machine_id": M2STUDIO_MACHINE,
        "pinned_sha": PINNED_UPSTREAM_SHA,
        "provider_env_names": sorted({spec.credential_env for spec in PROVIDERS.values()}),
        "secrets_recorded": False,
    }


def format_doctor(report: Mapping[str, object]) -> str:
    missing = report.get("missing")
    rows = missing if isinstance(missing, list) else []
    lines = [
        f"schema: {report.get('schema')}",
        f"status: {report.get('status')}",
        f"missing_count: {len(rows)}",
        "missing:",
    ]
    for item in rows:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _native_primary_present(home: Path, role: str) -> bool:
    try:
        spec, path = _native_primary_source(home, role)
        secrets = load_secrets(path)
        load_credential(spec, secrets.values)
    except (RuntimeRefusal, CredentialUnavailable, OSError, ValueError, KeyError):
        return False
    return True


def _native_primary_source(home: Path, role: str):
    from integrations.hermes_runtime.profile import load_profile
    installed = home / ".local" / "state" / f"hermes-runtime-{role}" / "current" / "profile.yaml"
    if installed.exists() or installed.is_symlink():
        profile = load_profile(installed)
        if profile.role != role:
            raise ValueError("installed role mismatch")
        return native_provider(role, profile.native_provider_id), profile.secrets_file
    return native_provider(role), home / ".config" / "hermes-runtime" / f"{role}.secrets.env"


def _credential_present(env: Mapping[str, str], env_name: str, file_name: str) -> bool:
    pointer = env.get(file_name)
    if pointer is not None and pointer != "":
        return _private_file(Path(pointer))
    return bool(env.get(env_name, "").strip())


def _private_file(path: Path) -> bool:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        return False
    try:
        info = os.fstat(fd)
    finally:
        os.close(fd)
    return stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1


def _gateway_file_ok(path: Path) -> bool:
    try:
        load_secrets(path)
    except (RuntimeRefusal, OSError):
        return False
    return True


def _agent_identity_gaps(home: Path, *, roster_path: Path | None = None) -> list[str]:
    """Per-agent Slack bot id and token. Names only; file bodies stay out."""

    path = roster_path or (Path(__file__).resolve().parents[1] / "hermes_secretary" / "roster.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [
            "credential:hermes-metaceo:HERMES_SLACK_BOT_TOKEN",
            "credential:hermes-secretary:HERMES_SLACK_BOT_TOKEN",
            "id:hermes-metaceo:HERMES_SLACK_BOT_USER_ID",
            "id:hermes-secretary:HERMES_SLACK_BOT_USER_ID",
        ]
    rows = data.get("hermes_agents") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return ["config:hermes_agents:invalid"]
    gaps: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        secrets_name = row.get("secrets_file")
        if not isinstance(name, str) or not isinstance(secrets_name, str):
            continue
        user_id, token = _slack_pair(home / ".config" / "hermes-runtime" / secrets_name)
        if not user_id:
            gaps.append(f"id:{name}:HERMES_SLACK_BOT_USER_ID")
        if not token:
            gaps.append(f"credential:{name}:HERMES_SLACK_BOT_TOKEN")
    return gaps


def _slack_pair(path: Path) -> tuple[bool, bool]:
    try:
        secrets = load_secrets(path)
    except (RuntimeRefusal, OSError):
        return False, False
    user_id = secrets.values.get("HERMES_SLACK_BOT_USER_ID", "")
    token = secrets.values.get("HERMES_SLACK_BOT_TOKEN", "")
    user_ok = bool(user_id) and user_id.startswith("U") and user_id.isalnum() and len(user_id) >= 7
    token_ok = (
        bool(token)
        and len(token) >= 16
        and not any(ch.isspace() for ch in token)
        and token.lower() not in {"changeme", "password", "secret", "token", "hermes", "replace-me"}
    )
    return user_ok, token_ok


def _upstream_attested(home: Path) -> bool:
    for role in ("mmsecretary", "mmmeta"):
        receipt = home / ".local" / "state" / f"hermes-runtime-{role}" / "current" / "install-receipt.json"
        try:
            payload = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("upstream_attested") is True and payload.get("sha") == PINNED_UPSTREAM_SHA:
            return True
    return False


def _systemd_user_manager() -> bool:
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "is-system-running"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    text = f"{proc.stdout or ''}{proc.stderr or ''}"
    if "Failed to connect" in text or "Failed to initialize" in text:
        return False
    return proc.returncode == 0 or "running" in text or "degraded" in text
