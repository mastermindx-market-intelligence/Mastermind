#!/usr/bin/env python3
"""Secret-free, load-aware host placement for remote sub-agent lanes."""
from __future__ import annotations

import argparse
import math
import json
import os
import stat
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from pool_status import HOSTS_JSON_PATH, HOSTS_STATE_DIR, window_state

MODE_TOOLS = {
    "go-codex": {"codex"},
    "qwen": {"codex"},
    "glm-codex": {"codex"},
    "minimax-codex": {"codex"},
    "glm": {"claude"},
    "minimax": {"claude"},
    "cursor": {"cursor-agent"},
    "grok": {"grok"},
    "codex-native": {"codex"}, "claude-native": {"claude"}, "oc-free": {"opencode"},
}
NO_HOST_RC = 3
MAX_STATE_BYTES = 1024 * 1024


def _as_float(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _as_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _finite_nonnegative(value: Any) -> Optional[float]:
    number = _as_float(value)
    return number if number is not None and number >= 0 and math.isfinite(number) else None


def _strict_nonnegative_int(value: Any) -> Optional[int]:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _positive_int(value: Any) -> Optional[int]:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0 and _finite_nonnegative(value) is not None:
        return value
    return None


def _valid_timestamp(value: Any, now: datetime) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        timestamp = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(timestamp) or timestamp <= 0:
        return None
    return timestamp if timestamp <= now.timestamp() + 1 else None


def _is_on_ac(value: Any) -> bool:
    if value is True:
        return True
    if value is False:
        return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("true", "1"):
            return True
        if normalized == "false":
            return False
    return False


def load_registry(path: str = HOSTS_JSON_PATH) -> Dict[str, Dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        document = json.load(handle)
    if not isinstance(document, dict):
        raise ValueError("hosts registry must be a JSON object")
    return {
        str(name): entry
        for name, entry in document.items()
        if not str(name).startswith("_") and isinstance(entry, dict)
    }


def load_state(state_dir: str, host: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(state_dir, f"{host}.json")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_STATE_BYTES:
                return None
            chunks = []
            total_size = 0
            while total_size <= MAX_STATE_BYTES:
                chunk = os.read(descriptor, MAX_STATE_BYTES + 1 - total_size)
                if not chunk:
                    break
                chunks.append(chunk)
                total_size += len(chunk)
            if total_size > MAX_STATE_BYTES:
                return None
            state = json.loads(b"".join(chunks).decode("utf-8"))
        finally:
            os.close(descriptor)
    except (OSError, UnicodeError, ValueError, TypeError):
        return None
    return state if isinstance(state, dict) else None


def _gate(
    name: str,
    ok: bool,
    label: str,
    detail: str = "",
) -> Dict[str, str]:
    return {
        "host": name,
        "gate": label,
        "result": "PASS" if ok else "FAIL",
        "detail": detail,
    }


def _tool_name(tool: Any) -> Optional[str]:
    if isinstance(tool, str):
        return tool
    if isinstance(tool, dict):
        name = tool.get("name")
        return name if isinstance(name, str) else None
    return None


def evaluate_hosts(
    registry: Dict[str, Dict[str, Any]],
    state_dir: str,
    mode: str,
    *,
    required_tools: Optional[Iterable[str]] = None,
    max_age: int = 180,
    excluded: Optional[Iterable[str]] = None,
    now: Optional[datetime] = None,
    states: Optional[Dict[str, Optional[Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    """Evaluate hosts without I/O beyond state files; never probes the network."""
    if mode not in MODE_TOOLS:
        raise ValueError(f"unknown mode: {mode}")
    if max_age < 0:
        raise ValueError("max-age must be non-negative")
    now = now or datetime.now(timezone.utc)
    tools = set(required_tools) if required_tools is not None else MODE_TOOLS[mode]
    excluded_hosts = set(excluded or ())
    rows: List[Dict[str, Any]] = []

    for name in sorted(registry):
        entry = registry[name]
        state = states.get(name) if states is not None else load_state(state_dir, name)
        gates: List[Dict[str, str]] = []

        roles = entry.get("roles") or []
        gates.append(_gate(name, "lanes" in roles, "roles", ",".join(map(str, roles))))
        allowed_modes = entry.get("allowed_modes")
        if allowed_modes is None:
            mode_ok = mode not in {"qwen", "go-codex", "grok", "cursor", "codex-native", "claude-native", "oc-free"}
            mode_detail = "explicit-mode-qualification-required" if not mode_ok else "legacy-unrestricted"
        elif (
            isinstance(allowed_modes, list)
            and all(isinstance(value, str) and value in MODE_TOOLS for value in allowed_modes)
            and len(set(allowed_modes)) == len(allowed_modes)
        ):
            mode_ok = mode in allowed_modes
            mode_detail = ",".join(allowed_modes) if allowed_modes else "none"
        else:
            mode_ok = False
            mode_detail = "invalid-policy"
        gates.append(_gate(name, mode_ok, "mode", mode_detail))
        qualification = entry.get("qualification_only_modes", [])
        qualification_valid = (
            isinstance(qualification, list)
            and all(isinstance(v, str) and v in MODE_TOOLS for v in qualification)
            and len(set(qualification)) == len(qualification)
        )
        gates.append(_gate(
            name, qualification_valid and mode not in qualification,
            "automatic-qualification",
            "invalid-policy" if not qualification_valid else (
                "explicit-canary-only" if mode in qualification else "not-held"
            ),
        ))
        gates.append(_gate(name, name not in excluded_hosts, "excluded"))

        state_ts = _valid_timestamp(state.get("ts"), now) if state else None
        # Never floor the elapsed duration before enforcing the freshness gate.
        # Doing so admits observations older than max_age by almost a second.
        elapsed_seconds = (
            max(0.0, now.timestamp() - state_ts)
            if state_ts is not None else None
        )
        state_age = int(elapsed_seconds) if elapsed_seconds is not None else None
        gates.append(
            _gate(
                name,
                state is not None and elapsed_seconds is not None
                and elapsed_seconds <= max_age,
                "fresh",
                "no-probe" if state_age is None else f"age={state_age}s",
            )
        )
        gates.append(
            _gate(
                name,
                bool(state and state.get("reachable") is True),
                "reachable",
                str((state or {}).get("error") or ""),
            )
        )

        window = window_state(entry.get("windows"), now)
        gates.append(_gate(name, window == "OPEN", "window", window))

        load1 = _as_float((state or {}).get("load1"))
        load_gate = _as_float(entry.get("load_gate"))
        gates.append(
            _gate(
                name,
                _finite_nonnegative(load1) is not None
                and load_gate is not None
                and load1 < load_gate,
                "load",
                "missing" if load1 is None or load_gate is None else f"{load1:g}<{load_gate:g}",
            )
        )
        if bool(entry.get("local")):
            gates.append(
                _gate(
                    name,
                    load1 is not None and load_gate is not None and load1 < load_gate,
                    "seat-load",
                    "missing" if load1 is None or load_gate is None else f"{load1:g}<{load_gate:g}",
                )
            )

        active_lanes = _strict_nonnegative_int((state or {}).get("active_lanes"))
        lane_ceiling = _positive_int(entry.get("lane_ceiling"))
        max_active = _positive_int(entry.get("max_active"))
        # Placement must respect both the physical ceiling and the launch gate.
        # Neither limit is capacity to spend when the other is missing/invalid.
        effective_ceiling = (
            min(lane_ceiling, max_active)
            if lane_ceiling is not None and max_active is not None and max_active <= 32
            else None
        )
        gates.append(
            _gate(
                name,
                active_lanes is not None
                and effective_ceiling is not None
                and active_lanes < effective_ceiling,
                "lane-ceiling",
                "reconciliation_hold" if active_lanes is None and (state or {}).get("active_lanes_status") == "held"
                else "missing_or_invalid" if active_lanes is None or effective_ceiling is None
                else f"{active_lanes}<{effective_ceiling} (lane_ceiling={lane_ceiling}, max_active={max_active})",
            )
        )

        disk_free = _finite_nonnegative((state or {}).get("disk_free_gb"))
        minimum_free = _finite_nonnegative(entry.get("min_free_gb"))
        # Optional staged-worktree allowance belongs to the existing host
        # disk gate. Do not admit one more 10+ GiB checkout at the base floor.
        reserve = _finite_nonnegative(entry.get("checkout_reserve_gb", 0))
        if reserve is not None and reserve > 128:
            reserve = None
        required_disk = (
            minimum_free + reserve
            if minimum_free is not None and reserve is not None else None
        )
        gates.append(
            _gate(
                name,
                disk_free is not None and required_disk is not None and disk_free >= required_disk,
                "disk",
                ("missing" if reserve == 0 else "missing-or-invalid")
                if disk_free is None or required_disk is None
                else (f"{disk_free:g}>={required_disk:g}" if reserve == 0
                      else f"{disk_free:g}>={required_disk:g} (base={minimum_free:g},stage={reserve:g})"),
            )
        )

        memory_floor_raw = entry.get("min_free_mem_gb")
        if memory_floor_raw is not None:
            memory_floor = _finite_nonnegative(memory_floor_raw)
            available_memory = _finite_nonnegative((state or {}).get("mem_free_gb"))
            gates.append(_gate(
                name,
                memory_floor is not None and available_memory is not None
                and available_memory >= memory_floor,
                "memory",
                "missing_or_invalid" if memory_floor is None or available_memory is None
                else f"{available_memory:g}>={memory_floor:g}",
            ))

        if bool(entry.get("require_ac")):
            on_ac = (state or {}).get("on_ac", "missing")
            gates.append(
                _gate(
                    name,
                    _is_on_ac(on_ac),
                    "ac",
                    str(on_ac),
                )
            )

        observed_tools = {_tool_name(tool) for tool in (state or {}).get("tools") or []}
        observed_tools.discard(None)
        missing = sorted(tools - observed_tools)
        gates.append(
            _gate(
                name,
                not missing,
                "tools",
                "all" if not missing else "missing=" + ",".join(missing),
            )
        )

        # Optional thermal admission guard applies only to explicitly enrolled
        # hosts. All unknown/malformed/stale readings HOLD new AUTO placement.
        # Existing worker processes are never killed or suspended here.
        if "require_thermal" in entry:
            thermal_required = entry["require_thermal"]
            therm = (state or {}).get("thermal")
            therm = therm if isinstance(therm, dict) else {}
            limit = _finite_nonnegative(entry.get("cpu_tctl_limit_c"))
            nvme_floor = _finite_nonnegative(entry.get("nvme_min_crit_headroom_c"))
            cpu = _finite_nonnegative(therm.get("cpu_tctl_c"))
            nvme = _as_float(therm.get("nvme_margin_crit_c"))
            therm_ts = _valid_timestamp(therm.get("observed_at"), now)
            therm_valid = (
                therm.get("schema") == "mastermind.fabric_host_thermal.v1"
                and therm.get("source") == "linux_hwmon"
                and therm.get("status") == "OBSERVED"
                and therm.get("admission_authoritative") is False
                and therm_ts is not None
                and state_ts is not None
                and abs(therm_ts - state_ts) <= 5
                and now.timestamp() - therm_ts <= max_age
                and cpu is not None and cpu >= 10
                and nvme is not None and math.isfinite(nvme)
                and _strict_nonnegative_int(therm.get("nvme_drive_count")) is not None
                and therm.get("nvme_drive_count") >= 1
            )
            policy_valid = (
                type(thermal_required) is bool
                and limit is not None and 50 <= limit <= 100
                and nvme_floor is not None and 3 <= nvme_floor <= 30
            )
            if thermal_required is False and policy_valid:
                gate_ok, detail = True, "policy-disabled"
            elif not policy_valid:
                gate_ok, detail = False, "invalid-thermal-policy"
            elif not therm_valid:
                gate_ok, detail = False, "thermal-unavailable-or-stale"
            elif cpu >= limit:
                gate_ok, detail = False, f"cpu_tctl={cpu:g}>={limit:g}C"
            elif nvme < nvme_floor:
                gate_ok, detail = False, f"nvme_crit_margin={nvme:g}<{nvme_floor:g}C"
            else:
                gate_ok, detail = True, f"cpu_tctl={cpu:g}<{limit:g}C,nvme_margin={nvme:g}>={nvme_floor:g}C"
            gates.append(_gate(name, gate_ok, "thermal", detail))
            # Cooldown is derived by the incumbent collector from the prior
            # observed snapshot, not from a new worker or health-control plane.
            # An absent legacy field preserves the old admission behavior.
            if thermal_required is True and "cooldown_until" in therm:
                until = therm.get("cooldown_until")
                valid_until = (
                    type(until) is int and therm_ts is not None
                    and therm_ts <= until <= therm_ts + 600
                    and until <= now.timestamp() + 600
                )
                remaining = max(0, int(math.ceil(until - now.timestamp()))) if valid_until else 0
                gates.append(_gate(
                    name,
                    valid_until and remaining == 0,
                    "thermal-recovery",
                    ("wait=%ss" % remaining if valid_until and remaining
                     else "recovered" if valid_until else "invalid-cooldown"),
                ))

        # Optional procfs pressure guard for specifically enrolled hosts only.
        # Existing workers continue; this is admission of new auto placements.
        if "require_pressure" in entry:
            required = entry.get("require_pressure")
            max_io = _finite_nonnegative(entry.get("max_io_psi_some10_pct"))
            max_mem = _finite_nonnegative(entry.get("max_memory_psi_some10_pct"))
            granular = (state or {}).get("granular")
            granular = granular if isinstance(granular, dict) else {}
            psi = granular.get("psi_some_avg10")
            psi = psi if isinstance(psi, dict) else {}
            io = _finite_nonnegative(psi.get("io"))
            memory_psi = _finite_nonnegative(psi.get("memory"))
            psi_ts = _valid_timestamp(granular.get("observed_at"), now)
            policy_valid = (
                type(required) is bool
                and max_io is not None and 1 <= max_io <= 100
                and max_mem is not None and 1 <= max_mem <= 100
            )
            observed = (
                granular.get("schema") == "mastermind.fabric_host_granular.v1"
                and granular.get("source") == "linux_procfs"
                and granular.get("admission_authoritative") is False
                and psi_ts is not None and state_ts is not None
                and abs(psi_ts - state_ts) <= 5
                and now.timestamp() - psi_ts <= max_age
                and io is not None and memory_psi is not None
            )
            if required is False and policy_valid:
                pressure_ok, why = True, "policy-disabled"
            elif not policy_valid:
                pressure_ok, why = False, "invalid-pressure-policy"
            elif not observed:
                pressure_ok, why = False, "pressure-unavailable-or-stale"
            elif io >= max_io:
                pressure_ok, why = False, f"io_psi_some10={io:g}>={max_io:g}%"
            elif memory_psi >= max_mem:
                pressure_ok, why = False, f"memory_psi_some10={memory_psi:g}>={max_mem:g}%"
            else:
                pressure_ok, why = True, f"io_psi={io:g}<{max_io:g}%,mem_psi={memory_psi:g}<{max_mem:g}%"
            gates.append(_gate(name, pressure_ok, "pressure", why))

        ncpu = _positive_int((state or {}).get("ncpu"))
        gates.append(
            _gate(
                name,
                ncpu is not None,
                "cpu",
                "missing" if ncpu is None else str(ncpu),
            )
        )

        eligible = all(item["result"] == "PASS" for item in gates)
        score: Optional[float] = None
        if eligible and effective_ceiling and active_lanes is not None and load1 is not None and ncpu:
            load_headroom = 1.0 - (load1 / ncpu)
            lane_headroom = (effective_ceiling - active_lanes) / effective_ceiling
            score = lane_headroom * 0.5 + load_headroom * 0.5
            # Existing validated thermal gate remains authoritative. Rank
            # eligible warm hosts below cooler alternatives before the hard
            # cutoff; advisory scoring grants no extra capacity or admission.
            if entry.get("require_thermal") is True:
                therm = (state or {}).get("thermal")
                therm = therm if isinstance(therm, dict) else {}
                tctl = _finite_nonnegative(therm.get("cpu_tctl_c"))
                ceiling = _finite_nonnegative(entry.get("cpu_tctl_limit_c"))
                if tctl is not None and ceiling is not None:
                    near_hot = min(1.0, max(0.0, (tctl - (ceiling - 25.0)) / 25.0))
                    score -= 0.20 * near_hot

        rows.append(
            {
                "host": name,
                "eligible": eligible,
                "seat": bool(entry.get("local")),
                "capacity_remaining": (max(0, effective_ceiling - active_lanes)
                     if type(effective_ceiling) is int and type(active_lanes) is int
                     else None),
                "ssh_alias": entry.get("ssh_alias"),
                "score": score,
                "age": state_age,
                "gates": gates,
            }
        )
    return rows


def prefer_remote_default() -> bool:
    """R34 (Chairman 2026-09-18): remote lanes hosts rank ahead of the seat host.
    Env HOST_PICK_PREFER_REMOTE=0 disables (seat competes on score, old tie-break)."""
    value = os.environ.get("HOST_PICK_PREFER_REMOTE", "1").strip().lower()
    return value not in ("0", "false", "no", "off")


def choose_host(rows: List[Dict[str, Any]],
                prefer_remote: Optional[bool] = None,
                placement_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Choose a safe host; spread concurrent near-equal candidates when keyed.

    HOST_PICK_SELECTION_KEY must be a unique task/attempt identity supplied by
    the existing launch owner. No new reservation/queue is created here.
    Without a key the historical deterministic ranking remains unchanged.
    Physical LaneLease still serializes and validates every final admission.
    """
    eligible = [row for row in rows if row["eligible"] and row["score"] is not None]
    if not eligible:
        return None
    if prefer_remote is None:
        prefer_remote = prefer_remote_default()
    if placement_key is None:
        placement_key = os.environ.get("HOST_PICK_SELECTION_KEY")
    if placement_key is not None:
        import re
        if (type(placement_key) is not str or
                re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}",
                             placement_key) is None):
            raise ValueError("host_pick_selection_key_invalid")
        # A fixed per-attempt key produces independent stable choices from the
        # SAME telemetry snapshot, avoiding a synchronized first-host stampede.
        # Normal capacity/health gating happens before this point. Constrain
        # hashing to near-equal candidates so a degraded host does not receive
        # work just because its hash is larger.
        import hashlib
        candidates = [r for r in eligible if not r["seat"]] if (
            prefer_remote and any(not r["seat"] for r in eligible)) else eligible
        highest = max(float(r["score"]) for r in candidates)
        near_equal = [r for r in candidates
                      if highest - float(r["score"]) <= 0.025]
        key_bytes = placement_key.encode("utf-8")
        # Weighted rendezvous avoids routing many concurrent tasks to a legacy
        # two-lane CI host when 25-slot adaptive hosts have equivalent scores.
        # Weight is bounded, advisory and never grants extra host slots.
        import math
        def placement_cost(row):
            h = hashlib.sha256(key_bytes + b"\0" +
                               row["host"].encode("utf-8")).digest()
            u = (int.from_bytes(h[:8], "big") + 1) / (2**64 + 1)
            remaining = row.get("capacity_remaining")
            weight = min(128, remaining) if type(remaining) is int and remaining > 0 else 1
            return -math.log(u) / weight
        return min(near_equal, key=placement_cost)
    if prefer_remote:
        # R34: every eligible remote host outranks the seat host regardless of score;
        # among remotes (and among seats) the existing score order still decides.
        key = lambda row: (bool(row["seat"]), -float(row["score"]), row["host"])
    else:
        key = lambda row: (-float(row["score"]), bool(row["seat"]), row["host"])
    return sorted(eligible, key=key)[0]


def refresh_stale(
    stale_hosts: Iterable[str],
    *,
    script: Optional[str] = None,
    runner=subprocess.run,
) -> bool:
    """Refresh only the supplied hosts; never called by evaluate_hosts.

    The selection is drained once and deduplicated in first-seen order, then
    handed to host_pull.sh as distinct ``--once --host HOST`` arguments
    (executed without a shell). An empty selection is a no-op success. Host
    name validity stays host_pull's job: a nonzero probe exit propagates as
    False, as does an unreadable/unrunnable probe.
    """
    selected = list(dict.fromkeys(stale_hosts or ()))
    if not selected:
        return True
    script = script or os.path.join(HERE, "host_pull.sh")
    argv = ["bash", script, "--once"]
    for host in selected:
        argv += ["--host", str(host)]
    try:
        completed = runner(argv, check=False, text=True, capture_output=True)
    except OSError:
        return False
    return completed.returncode == 0


def _print_host_lines(rows: List[Dict[str, Any]]) -> None:
    for row in rows:
        gates = "; ".join(
            f"{item['gate']}={item['result']}" + (f"({item['detail']})" if item["detail"] else "")
            for item in row["gates"]
        )
        score = "score=%.4f" % row["score"] if row["score"] is not None else "score=NA"
        print(f"{row['host']} {'ELIGIBLE' if row['eligible'] else 'INELIGIBLE'} {score} {gates}")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=sorted(MODE_TOOLS))
    parser.add_argument("--require-tool", action="append", default=[])
    parser.add_argument("--max-age", type=int, default=180)
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--seat-ok", action="store_true",
                        help="R34 off: let the seat host compete on score")
    parser.add_argument("--explain", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--hosts", help=argparse.SUPPRESS)
    parser.add_argument("--state-dir", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    hosts_path = args.hosts or os.environ.get("HOST_PICK_HOSTS", HOSTS_JSON_PATH)
    state_dir = args.state_dir or os.environ.get("HOST_PICK_STATE_DIR", HOSTS_STATE_DIR)
    try:
        registry = load_registry(hosts_path)
        rows = evaluate_hosts(
            registry,
            state_dir,
            args.mode,
            required_tools=(args.require_tool or None),
            max_age=args.max_age,
            excluded=args.exclude,
        )
        if args.refresh:
            # Retired, held or excluded hosts cannot become eligible by
            # refreshing telemetry. Probe only structurally qualified
            # candidates, not the decommissioned Mac minis.
            # Use fractional-precision freshness gate, not truncated age.
            structural = {"roles", "mode", "automatic-qualification", "excluded"}
            stale_hosts = [
                row["host"] for row in rows
                if all(g["result"] == "PASS" for g in row["gates"]
                       if g["gate"] in structural)
                and any(g["gate"] == "fresh" and g["result"] == "FAIL"
                        for g in row["gates"])
            ]
            if not refresh_stale(stale_hosts):
                print("REFRESH_FAILED", file=sys.stderr)
            rows = evaluate_hosts(
                registry,
                state_dir,
                args.mode,
                required_tools=(args.require_tool or None),
                max_age=args.max_age,
                excluded=args.exclude,
            )
        selected = choose_host(rows, prefer_remote=(False if args.seat_ok else None))
    except (OSError, ValueError) as exc:
        print(f"HOST_PICK_ERROR {type(exc).__name__}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"selected": selected["host"] if selected else None, "hosts": rows}, sort_keys=True))
    else:
        if args.explain:
            _print_host_lines(rows)
        print(selected["host"] if selected else "NONE")
    return 0 if selected else NO_HOST_RC


if __name__ == "__main__":
    raise SystemExit(main())
