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

from integrations.hermes_models.contract import PROVIDERS
from integrations.hermes_runtime.constants import PINNED_UPSTREAM_SHA
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.secrets import load_secrets

SCHEMA = "mastermind.hermes_harness.doctor.v1"
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
) -> dict:
    env = dict(os.environ if environ is None else environ)
    root = Path.home() if home is None else home
    missing: list[str] = []
    for env_name, file_name in _CREDENTIALS:
        if not _credential_present(env, env_name, file_name):
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
    if _chris_missing():
        missing.append("id:CHRIS_SLACK_USER_ID")
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


def _chris_missing() -> bool:
    path = Path(__file__).resolve().parents[1] / "hermes_secretary" / "roster.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    value = data.get("CHRIS_SLACK_USER_ID") if isinstance(data, dict) else None
    return not isinstance(value, str) or not value.strip()


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
