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
# The final installed release path. A unit may name the final release only,
# never a staging, archive or temporary path.
_RELEASE_ROOT_PATTERN = r"/opt/mastermind-executive/releases/[0-9a-f]{40}"


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


def _render_unit_text(*, role: str, service_name: str, runtime_user: str,
                      runtime_group: str, python_executable: str, release_root: str,
                      state_dir: str, restart_sec: float | int,
                      start_limit_burst: int, start_limit_interval_sec: int,
                      role_ip: str, implementation_sha: str | None,
                      secretary_enrollment: bool = False, meta_enrollment: bool = False) -> str:
    """The one shared pure unit formatter.

    Every value must already be qualified by its caller. The text, the
    restricted fragment paths, the isolated entry and the profile/bin paths
    are identical for the profile-facing renderer and for the closed
    installation-input consumer.
    """
    implementation_line = ("" if implementation_sha is None else
                           f"Environment=MM_HERMES_IMPLEMENTATION_SHA={implementation_sha}\n")
    if (type(secretary_enrollment) is not bool or type(meta_enrollment) is not bool
            or (secretary_enrollment and role != "mmsecretary")
            or (meta_enrollment and role != "mmmeta") or (secretary_enrollment and meta_enrollment)):
        raise RuntimeRefusal("ROOT_UNIT_ENROLLMENT_ROLE_INVALID")
    reload_command = ("enroll-secretary-session" if secretary_enrollment else
                      "enroll-meta-session" if meta_enrollment else "canary")
    reload_comment = ("# Operator-only original Secretary session enrollment; no provider prompt."
                      if secretary_enrollment else
                      "# Operator-only original Meta-CEO session enrollment; no provider prompt."
                      if meta_enrollment else
                      "# Operator-only provider-charged canary: requires separate authorization.")
    seconds = int(restart_sec) if float(restart_sec).is_integer() else restart_sec
    unit = f"""# ROOT-OWNED /etc/systemd/system/{service_name}.service
# Enforcing IPAddressDeny requires PID1's system manager; NEVER systemd --user.
# Role: {role}; pinned donor: {PINNED_UPSTREAM_SHA}
# A rendered unit is not host-kernel or provider acceptance.
[Unit]
Description=Mastermind Hermes {role} (root-managed cgroup, unprivileged process)
After=network-online.target hermes-egress.service
Wants=network-online.target
Requires=hermes-egress.service
BindsTo=hermes-egress.service
StartLimitIntervalSec={start_limit_interval_sec}
StartLimitBurst={start_limit_burst}

[Service]
Type=simple
NotifyAccess=main
User={runtime_user}
Group={runtime_group}
WorkingDirectory={state_dir}
ExecStart={python_executable} -I -S -B {release_root}/ops/executive_os/release_manifest.py hermes-runtime supervise --profile {state_dir}/current/profile.yaml --hermes-bin {state_dir}/current/bin/hermes
{reload_comment}
ExecReload={python_executable} -I -S -B {release_root}/ops/executive_os/release_manifest.py hermes-runtime {reload_command} --profile {state_dir}/current/profile.yaml --hermes-bin {state_dir}/current/bin/hermes
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
ReadWritePaths={state_dir}
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
    if re.fullmatch(_RELEASE_ROOT_PATTERN, root) is None:
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
    return _render_unit_text(
        role=profile.role, service_name=profile.service_name,
        runtime_user=runtime_user, runtime_group=runtime_group,
        python_executable=exe, release_root=root, state_dir=state,
        restart_sec=profile.restart_sec,
        start_limit_burst=profile.start_limit_burst,
        start_limit_interval_sec=profile.start_limit_interval_sec,
        role_ip=role_ip, implementation_sha=implementation_sha,
    )


def render_role_units_from_installation(installation, *, release_commit: str) -> dict[str, str]:
    """Render both role units from one closed approved installation input.

    The closed recipe supplies the role account, the state directory, the
    service bounds and the interpreter directly; no synthetic runtime
    profile is constructed and no unit text is duplicated here. The release
    path is the final installed release, never a staging or archive path.
    """
    from ops.executive_os.release_manifest import (
        ReleaseManifestError, linux_release_root, validate_hermes_runtime_installation,
    )

    try:
        document = validate_hermes_runtime_installation(installation)
    except ReleaseManifestError as exc:
        raise RuntimeRefusal("ROOT_UNIT_INSTALLATION_UNQUALIFIED") from exc
    if type(release_commit) is not str or re.fullmatch(r"[0-9a-f]{40}", release_commit) is None:
        raise RuntimeRefusal("ROOT_UNIT_IMPLEMENTATION_LABEL_INVALID")
    root = _safe_absolute(str(linux_release_root() / release_commit))
    if re.fullmatch(_RELEASE_ROOT_PATTERN, root) is None:
        raise RuntimeRefusal("ROOT_UNIT_RELEASE_PATH_INVALID")
    executable = _safe_absolute(document["launch_python"]["path"])
    rendered: dict[str, str] = {}
    for row in document["roles"]:
        role = row["role"]
        if role not in ROLE_PROXY_HOST:
            raise RuntimeRefusal("ROOT_UNIT_ROLE_INVALID")
        from .role_isolation import assert_service_account_names
        assert_service_account_names(role, role, role)
        rendered[role] = _render_unit_text(
            role=role, service_name=f"hermes-runtime-{role}",
            runtime_user=role, runtime_group=role,
            python_executable=executable, release_root=root,
            state_dir=_safe_absolute(row["state_dir"]),
            restart_sec=row["restart_sec"],
            start_limit_burst=row["start_limit_burst"],
            start_limit_interval_sec=row["start_limit_interval_sec"],
            role_ip=ROLE_PROXY_HOST[role], implementation_sha=release_commit,
            secretary_enrollment=(role == "mmsecretary" and "session_enrollment" in row.get("native_gateway", {})),
            meta_enrollment=(role == "mmmeta" and "session_enrollment" in row.get("native_gateway", {})),
        )
    return rendered


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
