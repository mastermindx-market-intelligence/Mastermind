"""Render a PID1-owned Hermes system unit, with no host side effects.

The ubuntu1 systemd --user instance cannot enforce IPAddressDeny without
root. A root-managed transient service using User=longr demonstrated
allow-own-proxy and deny-sibling/public. The existing Hermes process remains
unprivileged under the root-owned system manager.

This module only generates and validates unit text, and checks an exact
system-manager cgroup; it cannot install, restart, or enroll credentials.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

from .constants import CONFIG_EXIT, PINNED_UPSTREAM_SHA
from .egress import ROLE_PROXY_HOST
from .errors import RuntimeRefusal
from .profile import RuntimeProfile, load_profile

_UNSAFE = set(" \r\n\t\"'$\\%;") | {chr(96)}
_ACCOUNT = re.compile(r"[a-z_][a-z0-9_-]{0,31}\Z")


def _safe_absolute(value: str | Path) -> str:
    s = str(value)
    if not s.startswith("/") or any(c in s for c in _UNSAFE) or "//" in s:
        raise RuntimeRefusal("ROOT_UNIT_PATH_INVALID")
    if any(p in {".", ".."} for p in Path(s).parts):
        raise RuntimeRefusal("ROOT_UNIT_PATH_INVALID")
    return s


def assert_root_service_cgroup(role: str, *, raw: str | None = None) -> None:
    """The live caller MUST omit raw; it reads actual /proc/self/cgroup.

    A cgroup path alone still cannot prove effective BPF enforcement.
    """
    if role not in ROLE_PROXY_HOST:
        raise RuntimeRefusal("ROOT_UNIT_ROLE_INVALID")
    if raw is None:
        if not sys.platform.startswith("linux"):
            raise RuntimeRefusal("ROOT_UNIT_LINUX_REQUIRED")
        try:
            raw = Path("/proc/self/cgroup").read_text(encoding="ascii")
        except (OSError, UnicodeError):
            raise RuntimeRefusal("ROOT_UNIT_CGROUP_UNAVAILABLE") from None
    expected = f"/system.slice/hermes-runtime-{role}.service"
    if (not isinstance(raw, str) or len(raw) > 16384
            or not any(
                line.startswith("0::")
                and (line[3:] == expected or line[3:].startswith(expected + "/"))
                for line in raw.splitlines()
            )):
        raise RuntimeRefusal("ROOT_UNIT_CGROUP_UNQUALIFIED")


def assert_role_network_profile(profile: RuntimeProfile) -> None:
    """Require role-exclusive gateway/backend/proxy alias before any secrets."""
    if (type(profile) is not RuntimeProfile
            or profile.role not in ROLE_PROXY_HOST
            or profile.gateway_host != ROLE_PROXY_HOST[profile.role]):
        raise RuntimeRefusal("ROOT_UNIT_SHARED_LOOPBACK_REFUSED")


def render_host_unit(
    profile: RuntimeProfile, *, runtime_user: str, runtime_group: str,
    python_executable: str, repo_root: Path, implementation_sha: str | None = None,
) -> str:
    """An operator-reviewed SYSTEM unit; never installs or starts services."""
    if (type(profile) is not RuntimeProfile
            or profile.role not in ROLE_PROXY_HOST
            or profile.service_name != f"hermes-runtime-{profile.role}"
            or profile.sha != PINNED_UPSTREAM_SHA):
        raise RuntimeRefusal("ROOT_UNIT_PROFILE_UNQUALIFIED")
    if (not isinstance(runtime_user, str) or not _ACCOUNT.fullmatch(runtime_user)
            or runtime_user in {"root", "nobody"}
            or not isinstance(runtime_group, str) or not _ACCOUNT.fullmatch(runtime_group)
            or runtime_group in {"root", "nogroup"}):
        raise RuntimeRefusal("ROOT_UNIT_USER_UNQUALIFIED")
    from .role_isolation import assert_service_account_names
    from .tcp_sandbox import role_tcp_ports
    assert_service_account_names(profile.role, runtime_user, runtime_group)
    role_tcp_ports(profile)
    exe = _safe_absolute(python_executable)
    root = _safe_absolute(repo_root)
    if re.fullmatch(r"/opt/mastermind-executive/releases/[0-9a-f]{40}", root) is None:
        raise RuntimeRefusal("ROOT_UNIT_RELEASE_PATH_INVALID")
    state = _safe_absolute(profile.state_dir)
    secrets = _safe_absolute(profile.secrets_file)
    if (state == "/" or secrets == "/" or root == "/"
            or not profile.state_dir.is_absolute()
            or not profile.secrets_file.is_absolute()):
        raise RuntimeRefusal("ROOT_UNIT_PATH_INVALID")
    role_ip = ROLE_PROXY_HOST[profile.role]
    assert_role_network_profile(profile)
    if implementation_sha is not None and (
        type(implementation_sha) is not str or re.fullmatch(r"[0-9a-f]{40}", implementation_sha) is None
    ):
        raise RuntimeRefusal("ROOT_UNIT_IMPLEMENTATION_LABEL_INVALID")
    if implementation_sha is not None and implementation_sha != Path(root).name:
        raise RuntimeRefusal("ROOT_UNIT_IMPLEMENTATION_LABEL_MISMATCH")
    implementation_line = ("" if implementation_sha is None else
                           f"Environment=MM_HERMES_IMPLEMENTATION_SHA={implementation_sha}\n")
    seconds = int(profile.restart_sec) if float(profile.restart_sec).is_integer() else profile.restart_sec
    unit = f"""# ROOT-OWNED /etc/systemd/system/{profile.service_name}.service
# Enforcing IPAddressDeny requires PID1's system manager; NEVER systemd --user.
# Role: {profile.role}; pinned donor: {PINNED_UPSTREAM_SHA}
# A rendered unit is not host-kernel or provider acceptance.
[Unit]
Description=Mastermind Hermes {profile.role} (root-managed cgroup, unprivileged process)
After=network-online.target hermes-egress.service
Wants=network-online.target
Requires=hermes-egress.service
BindsTo=hermes-egress.service
StartLimitIntervalSec={profile.start_limit_interval_sec}
StartLimitBurst={profile.start_limit_burst}

[Service]
Type=simple
NotifyAccess=main
User={runtime_user}
Group={runtime_group}
WorkingDirectory={state}
ExecStart={exe} -I -S -B {root}/ops/executive_os/release_manifest.py hermes-runtime supervise --profile {state}/current/profile.yaml --hermes-bin {state}/current/bin/hermes
# Operator-only provider-charged canary: requires separate authorization.
ExecReload={exe} -I -S -B {root}/ops/executive_os/release_manifest.py hermes-runtime canary --profile {state}/current/profile.yaml --hermes-bin {state}/current/bin/hermes
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=PYTHONNOUSERSITE=1
{implementation_line}Restart=on-failure
RestartSec={seconds}
RestartPreventExitStatus={CONFIG_EXIT}
KillMode=control-group
TimeoutStopSec=15
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths={state}
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
CapabilityBoundingSet=
AmbientCapabilities=
UMask=0077
RestrictAddressFamilies=AF_UNIX AF_INET
IPAddressDeny=any
IPAddressAllow={role_ip}/32
RestrictSUIDSGID=true
LockPersonality=true
MemoryAccounting=true
TasksAccounting=true

[Install]
WantedBy=multi-user.target
"""
    allows = [line for line in unit.splitlines() if line.startswith("IPAddressAllow=")]
    if (allows != [f"IPAddressAllow={role_ip}/32"]
            or "EnvironmentFile=" in unit
            or "IPAddressAllow=localhost" in unit
            or "IPAddressAllow=any" in unit
            or unit.count("ExecStart=") != 1
            or unit.count("ExecReload=") != 1):
        raise RuntimeRefusal("ROOT_UNIT_GENERATION_UNSAFE")
    return unit


def main(argv: list[str] | None = None) -> int:
    """Print a source-only unit for root operator review, never install it."""
    p = argparse.ArgumentParser(prog="hermes-root-system-unit")
    p.add_argument("--profile", required=True, type=Path)
    p.add_argument("--user", required=True)
    p.add_argument("--group", required=True)
    p.add_argument("--python", required=True)
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--implementation-sha", help="Optional Mastermind source label; not installed-source attestation")
    a = p.parse_args(argv)
    try:
        print(render_host_unit(load_profile(a.profile),
              runtime_user=a.user, runtime_group=a.group,
              python_executable=a.python, repo_root=a.repo,
              implementation_sha=a.implementation_sha), end="")
    except RuntimeRefusal as exc:
        print(exc.code, file=sys.stderr)
        return CONFIG_EXIT
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
