"""Render a systemd --user unit. The unit is text only; it is not started here."""
from __future__ import annotations

from pathlib import Path

from .constants import CONFIG_EXIT, PINNED_UPSTREAM_SHA
from .errors import RuntimeRefusal
from .profile import RuntimeProfile

_UNSAFE = set(" \n\r\t\"'`$")


def _seconds(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(value)


def assert_systemd_user_dir(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.name != "user" or resolved.parent.name != "systemd":
        raise RuntimeRefusal("NOT_A_SYSTEMD_USER_DIRECTORY")
    banned = {
        Path("/etc/systemd/system"),
        Path("/lib/systemd/system"),
        Path("/usr/lib/systemd/system"),
        Path("/etc/systemd/user"),
        Path("/run/systemd/system"),
    }
    if resolved in banned or resolved.as_posix().startswith("/etc/systemd/system"):
        raise RuntimeRefusal("SYSTEM_UNIT_DIR_REFUSED")
    return resolved


def render_user_unit(
    profile: RuntimeProfile,
    *,
    python_executable: str,
    repo_root: Path,
) -> str:
    for label, value in (
        ("python", python_executable),
        ("repo", str(repo_root)),
        ("state", str(profile.state_dir)),
        ("profile", str(profile.state_dir / "current" / "profile.yaml")),
        ("bin", str(profile.state_dir / "current" / "bin" / "hermes")),
    ):
        if any(ch in value for ch in _UNSAFE):
            raise RuntimeRefusal("UNSAFE_PATH")
        if label == "python" and not value:
            raise RuntimeRefusal("UNSAFE_PATH")
    state = str(profile.state_dir)
    text = f"""# Mastermind Hermes runtime user unit. One unit per agent.
# Loopback only. No secrets in this file.
# HERMES_SLACK_BOT_USER_ID and HERMES_SLACK_BOT_TOKEN live in that unit's 0600 secrets file.
# Upstream pin {PINNED_UPSTREAM_SHA} is enforced by the profile loader.
[Unit]
Description=Mastermind Hermes runtime ({profile.role}, pinned loopback)
After=default.target
StartLimitIntervalSec={profile.start_limit_interval_sec}
StartLimitBurst={profile.start_limit_burst}

[Service]
Type=simple
WorkingDirectory={state}
ExecStart={python_executable} -m integrations.hermes_runtime supervise --profile {state}/current/profile.yaml --hermes-bin {state}/current/bin/hermes
Environment=PYTHONPATH={repo_root}
Environment=PYTHONDONTWRITEBYTECODE=1
Restart=on-failure
RestartSec={_seconds(profile.restart_sec)}
RestartPreventExitStatus={CONFIG_EXIT}
KillMode=control-group
TimeoutStopSec=15
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths={state}
UMask=0077
RestrictAddressFamilies=AF_UNIX AF_INET
IPAddressDeny=any
IPAddressAllow=localhost
RestrictSUIDSGID=true
LockPersonality=true
MemoryAccounting=true

[Install]
WantedBy=default.target
"""
    if "0.0.0.0" in text or "EnvironmentFile=" in text:
        raise RuntimeRefusal("UNIT_UNSAFE")
    return text
