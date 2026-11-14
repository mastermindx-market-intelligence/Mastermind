#!/usr/bin/env python3
"""Read-only Linux host instrumentation for Mastermind Fabric.

No root, network listener, credential access, or reservation side effects.
Output is observational: Fabric/Executive own admission decisions.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import socket
import time

SCHEMA = "mastermind.host_telemetry.v1"
KIB = 1024
GIB = 1024 ** 3


def safe_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None


def number(path: Path, divisor: float = 1) -> float | None:
    value = safe_text(path)
    try:
        return round(int(value) / divisor, 3) if value is not None else None
    except (TypeError, ValueError):
        return None


def sensors(hwmon: Path = Path("/sys/class/hwmon")) -> list[dict]:
    readings = []
    for folder in sorted(hwmon.glob("hwmon*")):
        chip = safe_text(folder / "name") or "unknown"
        for sensor in sorted(folder.glob("temp*_input")):
            stem = sensor.name[:-6]
            value = number(sensor, 1000)
            if value is None or not -50 <= value <= 150:
                continue
            item = {"chip": chip, "channel": stem,
                    "label": safe_text(folder / f"{stem}_label") or stem,
                    "celsius": value}
            for attr in ("max", "crit"):
                limit = number(folder / f"{stem}_{attr}", 1000)
                if limit is not None and 0 <= limit <= 150:
                    item[f"{attr}_celsius"] = limit
            readings.append(item)
    return readings


def fans(hwmon: Path = Path("/sys/class/hwmon")) -> list[dict]:
    result = []
    for folder in sorted(hwmon.glob("hwmon*")):
        chip = safe_text(folder / "name") or "unknown"
        for fan in sorted(folder.glob("fan*_input")):
            rpm = number(fan)
            if rpm is not None:
                result.append({"chip": chip, "channel": fan.name[:-6], "rpm": int(rpm)})
    return result


def cpu_ticks(proc: Path = Path("/proc")) -> dict[str, tuple[int, int]]:
    text = safe_text(proc / "stat") or ""
    ticks = {}
    for line in text.splitlines():
        cols = line.split()
        if not cols or not (cols[0] == "cpu" or (cols[0].startswith("cpu") and cols[0][3:].isdigit())):
            continue
        try:
            values = [int(x) for x in cols[1:9]]
        except ValueError:
            continue
        if len(values) == 8:
            ticks[cols[0]] = (sum(values), values[3] + values[4])
    return ticks


def cpu_usage(before: dict, after: dict) -> dict[str, float | None]:
    result = {}
    for name, (total, idle) in after.items():
        if name not in before:
            continue
        prior_total, prior_idle = before[name]
        elapsed = total - prior_total
        idle_diff = idle - prior_idle
        result[name] = round(max(0, min(100, 100 * (elapsed - idle_diff) / elapsed)), 1) if elapsed > 0 else None
    return result


def meminfo(proc: Path = Path("/proc")) -> dict[str, int | None]:
    data = {}
    for line in (safe_text(proc / "meminfo") or "").splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        fields = val.split()
        if fields and fields[0].isdigit() and (len(fields) == 1 or fields[1] == "kB"):
            data[key] = int(fields[0]) * (KIB if len(fields) > 1 else 1)
    return {name: data.get(name) for name in (
        "MemTotal", "MemAvailable", "SwapTotal", "SwapFree", "Cached", "Dirty", "Writeback", "Shmem")}


def pressure(proc: Path = Path("/proc")) -> dict:
    result = {}
    for kind in ("cpu", "memory", "io"):
        groups = {}
        for line in (safe_text(proc / "pressure" / kind) or "").splitlines():
            parts = line.split()
            if not parts:
                continue
            values = {}
            for token in parts[1:]:
                if "=" in token:
                    k, v = token.split("=", 1)
                    try:
                        values[k] = float(v) if k != "total" else int(v)
                    except ValueError:
                        pass
            groups[parts[0]] = values
        result[kind] = groups or None
    return result


def filesystems(root: Path = Path("/"), workspace: Path | None = None) -> dict:
    output = {}
    for name, directory in (("root", root), ("workspace", workspace)):
        if directory is None or not directory.exists():
            output[name] = None
            continue
        try:
            disk = shutil.disk_usage(directory)
            st = os.statvfs(directory)
            output[name] = {"free_bytes": disk.free, "total_bytes": disk.total,
                            "free_inodes": st.f_favail, "total_inodes": st.f_files}
        except OSError:
            output[name] = None
    return output



def frequencies(cpus: Path = Path("/sys/devices/system/cpu")) -> dict[str, float | None]:
    values = {}
    for core in sorted(cpus.glob("cpu[0-9]*"), key=lambda p: int(p.name[3:])):
        mhz = number(core / "cpufreq" / "scaling_cur_freq", 1000)
        values[core.name] = mhz
    return values


def interface_counters(net: Path = Path("/sys/class/net")) -> dict:
    result = {}
    for device in sorted(net.iterdir()) if net.exists() else []:
        if device.name == "lo":
            continue
        stats = device / "statistics"
        rx, tx = number(stats / "rx_bytes"), number(stats / "tx_bytes")
        if rx is not None and tx is not None:
            result[device.name] = {"rx_bytes": int(rx), "tx_bytes": int(tx),
                                   "carrier": number(device / "carrier"),
                                   "speed_mbps": number(device / "speed")}
    return result


def advisory(readings: list[dict], free_memory: int | None,
             free_disk: int | None) -> dict:
    alerts = []
    cpu = [r for r in readings if r["chip"] == "k10temp" and r["label"].lower() in ("tctl", "tdie")]
    cpu_temp = max((r["celsius"] for r in cpu), default=None)
    if cpu_temp is None:
        alerts.append({"severity": "unknown", "reason": "cpu_temperature_missing"})
    elif cpu_temp >= 92:
        alerts.append({"severity": "critical", "reason": "cpu_tctl_at_least_92c"})
    elif cpu_temp >= 85:
        alerts.append({"severity": "warning", "reason": "cpu_tctl_at_least_85c"})
    for row in readings:
        if row["chip"] != "nvme":
            continue
        if row["label"].lower() == "composite":
            # Hardware limits differ materially across NVMe drives. Prefer
            # measured sysfs max/critical thresholds to generic fallbacks;
            # leave headroom before controller throttling / critical temp.
            max_c, crit_c = row.get("max_celsius"), row.get("crit_celsius")
            warning_at = max(0, max_c - 5) if max_c is not None else 70
            critical_at = max(0, crit_c - 2) if crit_c is not None else (
                min(80, max_c + 1) if max_c is not None else 80)
            warning_at = min(warning_at, critical_at - 2)
        else:
            warning_at, critical_at = 85, 90
        severity = "critical" if row["celsius"] >= critical_at else (
            "warning" if row["celsius"] >= warning_at else None)
        if severity:
            alerts.append({"severity": severity, "reason": "nvme_temperature", "label": row["label"]})
    if free_memory is not None and free_memory < 4 * GIB:
        alerts.append({"severity": "warning", "reason": "available_memory_below_4gib"})
    if free_disk is not None and free_disk < 150 * GIB:
        alerts.append({"severity": "warning", "reason": "workspace_disk_below_150gib"})
    level = "critical" if any(a["severity"] == "critical" for a in alerts) else (
        "warning" if any(a["severity"] == "warning" for a in alerts) else
        "unknown" if any(a["severity"] == "unknown" for a in alerts) else "nominal")
    return {"level": level, "alerts": alerts, "admission_authoritative": False,
            "policy": "ADVISORY_ONLY: Fabric owns worker admission"}


def observe(sample_seconds: float = 0.2, *, proc: Path = Path("/proc"),
            hwmon: Path = Path("/sys/class/hwmon"), workspace: Path | None = None) -> dict:
    before = cpu_ticks(proc)
    time.sleep(max(0.05, min(1.0, sample_seconds)))
    after = cpu_ticks(proc)
    mem, thermal = meminfo(proc), sensors(hwmon)
    disks = filesystems(workspace=workspace)
    try:
        load = list(os.getloadavg())
    except OSError:
        load = None
    usage = cpu_usage(before, after)
    return {"schema": SCHEMA, "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "hostname": socket.gethostname(), "read_only": True,
            "cpu": {"logical_count": os.cpu_count(), "utilization_pct": usage.get("cpu"),
                    "per_core_utilization_pct": {k: v for k, v in usage.items() if k != "cpu"},
                    "load_1_5_15": load,
                    "governor": safe_text(Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")),
                    "per_core_frequency_mhz": frequencies()},
            "memory_bytes": mem, "psi": pressure(proc), "filesystems": disks,
            "temperatures": thermal, "fans": fans(hwmon), "network": interface_counters(),
            "advisory": advisory(thermal, mem.get("MemAvailable"),
                                 (disks.get("workspace") or disks.get("root") or {}).get("free_bytes"))}


def persist(observation: dict, directory: Path) -> None:
    """Atomic current snapshot + capped local sample history, without any listener."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = json.dumps(observation, sort_keys=True, separators=(",", ":")) + "\n"
    tmp = directory / f"latest.{os.getpid()}.tmp"
    try:
        tmp.write_text(payload, encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, directory / "latest.json")
        history = directory / "history.ndjson"
        if history.exists() and history.stat().st_size > 8 * 1024 * 1024:
            history.replace(directory / "history.previous.ndjson")
        with history.open("a", encoding="utf-8") as f:
            f.write(payload)
        os.chmod(history, 0o600)
    finally:
        tmp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mastermind read-only host sensors / load / PSI")
    parser.add_argument("--sample-ms", type=int, default=200)
    parser.add_argument("--store", action="store_true", help="Save restricted local latest + rolling history")
    parser.add_argument("--quiet", action="store_true", help="Suppress stdout for systemd service")
    args = parser.parse_args(argv)
    result = observe(args.sample_ms / 1000, workspace=Path.home() / "lanes")
    if args.store:
        state = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "mastermind-host-telemetry"
        persist(result, state)
    if not args.quiet:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
