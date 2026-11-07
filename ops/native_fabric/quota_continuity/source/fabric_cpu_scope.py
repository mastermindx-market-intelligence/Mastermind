#!/usr/bin/env python3
"""Optional Linux CPU budget beneath the original Fabric LaneLease.

NOT a scheduler, lease, retry authority or daemon. The original remote_sub_exec
still owns worker START and settlement. The quota is per original run, and
post-run verification requires the entire user-owned cgroup to be empty.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Mapping, Sequence


class CpuScopeRefused(ValueError):
    """Before first process scope write; never fallback to unbounded execution."""


class CpuScopeEffectUnknown(RuntimeError):
    """A scope might contain live descendants. Preserve original Fabric lease."""


@dataclass(frozen=True)
class CpuScopePlan:
    unit: str
    quota_percent: int
    env: dict[str, str]
    command: tuple[str, ...]
    cgroup_path: Path


_MODES = frozenset({"glm", "glm-codex", "minimax", "qwen"})
_HOSTS = frozenset({"ubuntu2", "ubuntu3"})
_QUOTAS = frozenset({"100", "200", "400"})
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")


def _properties(unit: str, env: Mapping[str, str]) -> dict[str, str]:
    try:
        q = subprocess.run(
            ["/usr/bin/systemctl", "--user", "show", unit,
             "--property=LoadState,ActiveState,ControlGroup", "--no-pager"],
            env=dict(env), capture_output=True, text=True, timeout=4,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CpuScopeEffectUnknown("cpu_scope_manager_unavailable") from exc
    if q.returncode != 0 or len(q.stdout) > 2048:
        raise CpuScopeEffectUnknown("cpu_scope_status_unverifiable")
    values = {}
    for line in q.stdout.splitlines():
        if "=" not in line:
            raise CpuScopeEffectUnknown("cpu_scope_status_malformed")
        k, v = line.split("=", 1)
        if k in values or k not in ("LoadState", "ActiveState", "ControlGroup"):
            raise CpuScopeEffectUnknown("cpu_scope_status_malformed")
        values[k] = v
    if set(values) != {"LoadState", "ActiveState", "ControlGroup"}:
        raise CpuScopeEffectUnknown("cpu_scope_status_missing_fields")
    return values


def _remaining_pids(path: Path) -> list[int]:
    # The exact path belongs to a hashed, newly created original-run scope.
    if not path.exists():
        return []
    try:
        s = path.lstat()
        if not stat.S_ISDIR(s.st_mode) or path.is_symlink():
            raise CpuScopeEffectUnknown("cpu_scope_cgroup_path_unsafe")
        data = (path / "cgroup.procs").read_text(encoding="ascii")
        if len(data) > 8192:
            raise CpuScopeEffectUnknown("cpu_scope_procs_too_large")
        values = [int(x) for x in data.split()]
        if any(x <= 0 for x in values):
            raise CpuScopeEffectUnknown("cpu_scope_procs_invalid")
        return values
    except (OSError, ValueError) as exc:
        raise CpuScopeEffectUnknown("cpu_scope_procs_unreadable") from exc


def prepare_scope(
    key: str,
    mode: str,
    command: Sequence[str],
    env: Mapping[str, str],
) -> CpuScopePlan | None:
    """Validate a *new original worker* and preflight the user systemd scope.

    Caller MUST already hold its incumbent physical LaneLease and provider
    custody; this helper neither acquires nor asserts those permissions.
    """
    raw = env.get("FABRIC_CPU_SCOPE_QUOTA_PCT", "")
    if not raw:
        return None
    if (raw not in _QUOTAS or sys.platform != "linux"
            or env.get("LANE_REMOTE_HOST") not in _HOSTS or mode not in _MODES
            or _RUN_ID.fullmatch(key) is None
            or env.get("REMOTE_SUB_RUN_ID") != key
            or not all(isinstance(env.get(f), str) and
                       0 < len(env[f]) <= 256
                       for f in ("POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID",
                                 "POOL_LEASE_ID", "SUPPORT_DIGEST"))
            or not command or any(type(c) is not str or not c or "\x00" in c
                                   for c in command)):
        raise CpuScopeRefused("cpu_scope_qualification_refused")
    uid = os.getuid()
    bus = Path("/run/user") / str(uid) / "bus"
    try:
        info = bus.lstat()
        if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != uid
                or bus.is_symlink()):
            raise CpuScopeRefused("cpu_scope_user_bus_unqualified")
    except OSError as exc:
        raise CpuScopeRefused("cpu_scope_user_bus_unavailable") from exc
    user_env = dict(env)
    user_env["XDG_RUNTIME_DIR"] = str(bus.parent)
    user_env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=" + str(bus)
    for path in ("/usr/bin/systemd-run", "/usr/bin/systemctl", "/usr/bin/env"):
        if not Path(path).is_file() or not os.access(path, os.X_OK):
            raise CpuScopeRefused("cpu_scope_runtime_unavailable")
    binding = json.dumps([key, env["POOL_LEASE_ID"],
                          env["POOL_ORCHESTRATOR_ID"],
                          env["POOL_PARENT_RUN_ID"],
                          env["LANE_REMOTE_HOST"],
                          env["SUPPORT_DIGEST"]], separators=(",", ":"))
    unit = "mmx-fabric-cpu-" + hashlib.sha256(binding.encode()).hexdigest()[:28] + ".scope"
    cgroup = (Path("/sys/fs/cgroup/user.slice") / ("user-" + str(uid) + ".slice") /
              ("user@" + str(uid) + ".service") / "app.slice" / unit)
    try:
        state = _properties(unit, user_env)
        if (state["LoadState"] != "not-found" or
                state["ActiveState"] != "inactive" or state["ControlGroup"] or
                cgroup.exists()):
            raise CpuScopeRefused("cpu_scope_preexisting_run_refused")
    except CpuScopeEffectUnknown as exc:
        raise CpuScopeRefused(str(exc)) from exc
    # Using /usr/bin/env strips user-bus metadata from the actual provider.
    # The newly created unit itself is bounded by CPUQuota for all descendants.
    scoped_command = (
        "/usr/bin/systemd-run", "--user", "--scope", "--quiet", "--collect",
        "--slice=app.slice", "--unit=" + unit,
        "-p", "CPUQuota=" + raw + "%",
        "/usr/bin/env", "-u", "DBUS_SESSION_BUS_ADDRESS",
        "-u", "XDG_RUNTIME_DIR", "-u", "FABRIC_CPU_SCOPE_QUOTA_PCT",
        *tuple(command),
    )
    return CpuScopePlan(unit, int(raw), user_env, scoped_command, cgroup)


def settle_scope(plan: CpuScopePlan) -> dict[str, object]:
    """Account for detached descendants before existing Fabric lease release.

    Any unreadable/unknown/occupied result is EFFECT_UNKNOWN. This function
    never touches other units; only the exact original-run hashed scope name.
    """
    before = _properties(plan.unit, plan.env)
    desired_path = "/" + str(plan.cgroup_path).removeprefix("/sys/fs/cgroup/").lstrip("/")
    if (before["ControlGroup"] and
            before["ControlGroup"] != desired_path):
        raise CpuScopeEffectUnknown("cpu_scope_owner_mismatch")
    if before["LoadState"] not in ("loaded", "not-found"):
        raise CpuScopeEffectUnknown("cpu_scope_state_unknown")
    if before["LoadState"] == "not-found" and (
            before["ActiveState"] != "inactive" or before["ControlGroup"]):
        raise CpuScopeEffectUnknown("cpu_scope_unexpected_missing_state")
    pids_before = _remaining_pids(plan.cgroup_path)
    needed_stop = before["LoadState"] == "loaded" and (
        before["ActiveState"] != "inactive" or bool(pids_before)
    )
    if needed_stop:
        try:
            p = subprocess.run(
                ["/usr/bin/systemctl", "--user", "stop", plan.unit],
                env=plan.env, capture_output=True, text=True, timeout=8,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CpuScopeEffectUnknown("cpu_scope_stop_unverifiable") from exc
        if p.returncode:
            raise CpuScopeEffectUnknown("cpu_scope_stop_refused")
    after = _properties(plan.unit, plan.env)
    if (after["ActiveState"] != "inactive" or
            after["LoadState"] not in ("loaded", "not-found") or
            (after["ControlGroup"] and after["ControlGroup"] != desired_path) or
            _remaining_pids(plan.cgroup_path)):
        raise CpuScopeEffectUnknown("cpu_scope_descendants_not_settled")
    return {
        "schema": "mastermind.fabric_cpu_scope_settlement.v1",
        "unit": plan.unit,
        "quota_percent": plan.quota_percent,
        "killed_remaining_child_processes": bool(pids_before),
        "stop_issued": needed_stop,
        "remaining_pids": 0,
        "scope_inactive": True,
    }
