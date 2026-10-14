"""Read-only diagnostics over the existing Fabric observer, never admission.

This module owns a bounded presentation, not collection, history retention,
physical identity, worker lifecycle, scheduling, or hardware control.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import stat
import time
from datetime import datetime

from common.fleet_health_contract import (FLEET_SCHEMA as SCHEMA, FLEET_WINDOWS as WINDOWS,
    FLEET_MAX_RESPONSE_BYTES as MAX_RESPONSE_BYTES, FLEET_MAX_AGE as MAX_AGE)

MAX_HOSTS = 32
MAX_POINTS = 360
MAX_HISTORY_BYTES = 32 * 1024 * 1024  # overall bounded 30-day source ceiling
# Keep short views inexpensive at the incumbent observer's ~0.6 MiB/day.
_WINDOW_HISTORY_BYTES = {"1h": 1 * 1024 * 1024, "24h": 2 * 1024 * 1024,
                         "7d": 8 * 1024 * 1024, "30d": MAX_HISTORY_BYTES}
GIB = 1024 ** 3
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}\Z")
_LOG = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?Z) \[pull\] host=([A-Za-z0-9_.:-]+) rc=(-?\d+) secs=\d+ (.*)$")
METRICS = ("cpu_busy_pct", "load1", "load5", "logical_cpus",
           "memory_available_bytes", "memory_total_bytes", "memory_used_pct",
           "swap_used_bytes", "cpu_temp_c", "nvme_temp_c", "fan_rpm",
           "disk_free_bytes", "fabric_active_lanes", "process_lane_candidates",
           "thermal_advisory_c")
HISTORY_METRICS = ("cpu_temp_c", "cpu_busy_pct", "load1", "memory_used_pct", "fabric_active_lanes")


def _number(value, low=0, high=2 ** 53 - 1, *, integer=False):
    if type(value) not in (int, float):
        return None
    try:
        if not math.isfinite(value) or not low <= value <= high:
            return None
    except (OverflowError, TypeError):
        return None
    if integer and int(value) != value:
        return None
    return int(value) if integer else value


def _inputs(window, now):
    if type(window) is not str or window not in WINDOWS or _number(now, 1) is None:
        raise ValueError("invalid Fleet read")


def unavailable_fleet(window, now, reason="SOURCE_UNAVAILABLE"):
    _inputs(window, now)
    if reason not in ("SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "REGISTRY_INVALID", "RESPONSE_OVER_BUDGET"):
        raise ValueError("invalid Fleet refusal")
    return {"schema": SCHEMA, "availability": "UNAVAILABLE", "generated_at": now,
            "window": window, "history_truncated": False, "admission_authoritative": False,
            "source": "fabric_host_observer", "hosts": [], "reason_codes": [reason]}


def _registered(registry):
    if type(registry) is not dict:
        raise ValueError("registry invalid")
    entries = {}
    for key, value in registry.items():
        if type(key) is not str:
            raise ValueError("registry invalid")
        if key.startswith("_"):  # incumbent owner metadata, never a machine
            continue
        if not _ID.fullmatch(key) or type(value) is not dict:
            raise ValueError("registry invalid")
        entries[key] = value
    if not entries or len(entries) > MAX_HOSTS:
        raise ValueError("registry invalid")
    # The registry explicitly sends these named aliases to the same primary
    # transport. Never add shadow occupancy to the primary or infer other
    # physical equivalences from IP, free-form notes, hostname or CPU model.
    grouped = set()
    for key, value in tuple(entries.items()):
        alias = value.get("ssh_alias")
        if (type(alias) is str and alias != key and alias in entries
                and entries[alias].get("ssh_alias") == alias
                and value.get("platform") == entries[alias].get("platform")):
            grouped.add(alias)
            del entries[key]
    return entries, grouped


def _nested(source, key, schema, timestamp, allowed_sources):
    value = source.get(key)
    if (type(value) is dict and value.get("schema") == schema
            and type(value.get("observed_at")) in (int, float)
            and value.get("observed_at") == timestamp
            and value.get("source") in allowed_sources):
        return value
    return {}


def _snapshot(host, entry, source, now):
    metrics = dict.fromkeys(METRICS)
    coverage = ["SUBAGENT_COVERAGE_PARTIAL"]
    if type(source) is not dict or source.get("host") != host:
        return "UNKNOWN", None, metrics, coverage + ["SNAPSHOT_UNAVAILABLE"], {}
    stamp = _number(source.get("ts"), 1, now)
    if stamp is None:
        return "UNKNOWN", None, metrics, coverage + ["OBSERVATION_TIME_INVALID"], {}
    reachable = source.get("reachable")
    state = "STALE" if now - stamp > MAX_AGE else (
        "CURRENT" if reachable is True else "OFFLINE" if reachable is False else "UNKNOWN")
    if reachable is not True:
        return state, stamp, metrics, coverage + ["SNAPSHOT_UNAVAILABLE"], {}
    g = _nested(source, "granular", "mastermind.fabric_host_granular.v1", stamp,
                {"linux_procfs", "macos_host_statistics"})
    t = _nested(source, "thermal", "mastermind.fabric_host_thermal.v1", stamp,
                {"linux_hwmon", "macos_thermal"})
    metrics.update(cpu_busy_pct=_number(g.get("cpu_busy_pct"), 0, 100),
                   load1=_number(source.get("load1")), load5=_number(source.get("load5")),
                   logical_cpus=_number(source.get("ncpu"), 1, 65536, integer=True),
                   memory_available_bytes=_number(g.get("mem_available_bytes")),
                   memory_total_bytes=_number(g.get("mem_total_bytes"), 1),
                   swap_used_bytes=_number(g.get("swap_used_bytes")),
                   cpu_temp_c=_number(t.get("cpu_tctl_c"), 0, 150),
                   nvme_temp_c=_number(t.get("nvme_hottest_c"), 0, 150),
                   fan_rpm=_number(t.get("cpu_fan_rpm"), 0, 100000),
                   process_lane_candidates=_number(source.get("process_active_lanes"), integer=True),
                   thermal_advisory_c=_number(entry.get("cpu_tctl_limit_c"), 1, 150))
    if metrics["memory_available_bytes"] is None:
        free = _number(source.get("mem_free_gb"), 0, 1_000_000)
        if free is not None:
            metrics["memory_available_bytes"] = round(free * GIB)
            if entry.get("platform") == "darwin":
                coverage.append("MAC_MEMORY_FREE_INACTIVE_ESTIMATE")
    total, available = metrics["memory_total_bytes"], metrics["memory_available_bytes"]
    if total is not None and available is not None:
        if available <= total:
            metrics["memory_used_pct"] = round(100 * (1 - available / total), 2)
        else:
            metrics["memory_total_bytes"] = None
            coverage.append("MEMORY_SOURCE_INCONSISTENT")
    disk = _number(source.get("disk_free_gb"), 0, 1_000_000_000)
    metrics["disk_free_bytes"] = round(disk * GIB) if disk is not None else None
    occupancy = _number(source.get("active_lanes"), integer=True)
    lane = source.get("lane_occupancy")
    if type(lane) is dict and (type(lane.get("active")) not in (int, float)
                              or _number(lane.get("active"), integer=True) != occupancy):
        occupancy = None
        coverage.append("OCCUPANCY_CONFLICT")
    if source.get("active_lanes_status") == "known":
        metrics["fabric_active_lanes"] = occupancy
    for key, reason in (("cpu_temp_c", "CPU_TEMPERATURE_UNAVAILABLE"),
                        ("cpu_busy_pct", "CPU_UTILIZATION_UNAVAILABLE"),
                        ("memory_total_bytes", "MEMORY_TOTAL_UNAVAILABLE"),
                        ("thermal_advisory_c", "THERMAL_ADVISORY_UNAVAILABLE")):
        if metrics[key] is None:
            coverage.append(reason)
    if state != "CURRENT":
        coverage.append("SNAPSHOT_NOT_CURRENT")
    return state, stamp, metrics, coverage, t


def _history(text, hosts, now, window):
    histories = {key: [] for key in hosts}
    conflicts = set()
    if type(text) is not str:
        return histories, conflicts
    for line in text.splitlines():
        if len(line) > 2048:
            continue
        match = _LOG.fullmatch(line)
        if not match or match[2] not in histories:
            continue
        try:
            stamp = datetime.fromisoformat(match[1].replace("Z", "+00:00")).timestamp()
        except (ValueError, OverflowError):
            continue
        if not now - WINDOWS[window] <= stamp <= now:
            continue
        fields = {}
        for token in match[4].split():
            key, sep, value = token.partition("=")
            if not sep or key in fields:
                fields = {}
                break
            fields[key] = value
        if fields.get("reachable") not in ("true", "false"):
            continue
        point = {"timestamp": stamp, **dict.fromkeys(HISTORY_METRICS)}
        if fields["reachable"] == "true" and match[3] == "0":
            for output, raw, high, integer in (
                    ("cpu_temp_c", "tctl_c", 150, False),
                    ("cpu_busy_pct", "cpu_busy_pct", 100, False),
                    ("load1", "load1", 2 ** 53 - 1, False),
                    ("memory_used_pct", "memory_used_pct", 100, False),
                    ("fabric_active_lanes", "active_lanes", 2 ** 53 - 1, True)):
                try:
                    value = float(fields[raw])
                except (KeyError, ValueError, OverflowError):
                    continue
                point[output] = _number(value, 0, high, integer=integer)
        series = histories[match[2]]
        if series and stamp < series[-1]["timestamp"]:
            conflicts.add(match[2])
            continue
        if series and stamp == series[-1]["timestamp"]:
            if point != series[-1]:
                series[-1] = {"timestamp": stamp, **dict.fromkeys(HISTORY_METRICS)}
            continue
        series.append(point)
    for host in conflicts:
        histories[host] = []
    return histories, conflicts


def _duration(series, metric, threshold, now):
    if not series or now - series[-1]["timestamp"] > MAX_AGE:
        return 0
    end = start = series[-1]["timestamp"]
    previous = end
    for point in reversed(series):
        value = point[metric]
        if value is None or value < threshold or previous - point["timestamp"] > MAX_AGE:
            break
        start = previous = point["timestamp"]
    return end - start


def _finding(code, severity, category, summary, detail, duration=None):
    return {"code": code, "severity": severity, "category": category,
            "summary": summary, "detail": detail, "duration_seconds": duration}


def _findings(state, metrics, series, thermal, now):
    if state != "CURRENT":
        return [_finding("CURRENT_HEALTH_UNKNOWN", "info", "coverage", "Current health is unknown",
                         "This machine has no current successful observation. Restore its existing observer connection; old readings are not a healthy or idle verdict.")]
    result = []
    limit, temperature = metrics["thermal_advisory_c"], metrics["cpu_temp_c"]
    if limit is not None and temperature is not None and temperature >= limit:
        duration = _duration(series, "cpu_temp_c", limit, now)
        result.append(_finding(
            "SUSTAINED_THERMAL_HEADROOM" if duration >= 600 else "THERMAL_HEADROOM_LOW",
            "warning", "hardware", "Sustained limited thermal headroom" if duration >= 600 else "Limited thermal headroom",
            f"CPU temperature is at or above the current {limit:g}°C Fabric operator advisory limit. This is not a manufacturer damage threshold or proof of damage. Review future concurrency through existing placement and inspect airflow/cooling. Monitoring does not cool the machine.", duration))
    busy = metrics["cpu_busy_pct"]
    duration = _duration(series, "cpu_busy_pct", 90, now)
    if busy is not None and busy >= 90 and duration >= 1800:
        result.append(_finding("SUSTAINED_CPU_PRESSURE", "warning", "performance", "Sustained CPU saturation",
            "CPU busy time has remained at least 90% for 30 minutes in contiguous observations. Consider deferring or redistributing future work through the existing scheduler. Heavy CPU use alone is not evidence of hardware damage.", duration))
    # Some Macs expose load average but no CPU-busy sensor through the
    # incumbent collector. Only report sustained *performance* pressure from
    # normalized load; never infer heat, wear, or a damage threshold.
    load, cores = metrics["load1"], metrics["logical_cpus"]
    if busy is None and load is not None and cores is not None and load >= 1.5 * cores:
        duration = _duration(series, "load1", 1.5 * cores, now)
        if duration >= 1800:
            result.append(_finding("SUSTAINED_LOAD_PRESSURE", "warning", "performance", "Sustained elevated host load",
                "One-minute load average has remained at least 1.5 times logical CPU count for 30 minutes. Load average is not CPU busy time or a temperature reading; it can reflect runnable and uninterruptible tasks. Investigate process/IO pressure and consider shifting future work through the existing Capacity owner. This is not evidence of hardware damage.", duration))
    margin = _number(thermal.get("nvme_margin_crit_c"), -150, 150)
    if margin is not None and margin <= 0 and metrics["nvme_temp_c"] is not None:
        result.append(_finding("NVME_CRITICAL_TEMPERATURE", "critical", "hardware", "Storage thermal limit observed",
            "The existing sensor reports no remaining margin to its NVMe critical temperature. Reduce avoidable new I/O through existing controls and have an operator inspect storage cooling. This is a reported sensor warning, not a prediction of failure."))
    return result


def _downsample(series):
    if len(series) <= MAX_POINTS:
        selected = range(len(series))
    else:
        # Retain four temporal segments per bucket as well as genuine
        # per-metric extremes. Five time anchors + at most ten extrema keep
        # the global 360-point ceiling without flattening long steady trends.
        size = math.ceil(len(series) / (MAX_POINTS // 15))
        selected = set()
        for start in range(0, len(series), size):
            end = min(len(series), start + size)
            span = end - start - 1
            selected.update(start + round(span * fraction)
                            for fraction in (0, 0.25, 0.5, 0.75, 1))
            for key in HISTORY_METRICS:
                indices = [i for i in range(start, end) if series[i][key] is not None]
                if indices:
                    selected.update((min(indices, key=lambda i: series[i][key]),
                                     max(indices, key=lambda i: series[i][key])))
        selected = sorted(selected)
    result, previous = [], 0
    for i in selected:
        temporal_gap = any(series[j]["timestamp"] - series[j - 1]["timestamp"] > MAX_AGE
                           for j in range(previous + 1, i + 1))
        gaps = [key for key in HISTORY_METRICS if temporal_gap or
                any(series[j][key] is None for j in range(previous, i + 1))] if result else []
        result.append({**series[i], "gaps": gaps})
        previous = i
    return result


def compose_fleet_health(registry, snapshots, log_text, *, window, now, history_truncated=False):
    _inputs(window, now)
    if type(history_truncated) is not bool:
        raise ValueError("invalid history truncation")
    try:
        entries, grouped = _registered(registry)
    except ValueError:
        return unavailable_fleet(window, now, "REGISTRY_INVALID")
    if type(snapshots) is not dict or type(log_text) is not str:
        return unavailable_fleet(window, now)
    if len(log_text.encode("utf-8")) > MAX_HISTORY_BYTES:
        return unavailable_fleet(window, now, "RESPONSE_OVER_BUDGET")
    histories, conflicts = _history(log_text, entries, now, window)
    hosts = []
    for host, entry in sorted(entries.items()):
        state, stamp, metrics, coverage, thermal = _snapshot(host, entry, snapshots.get(host), now)
        series = histories[host]
        if (state == "CURRENT" and stamp is not None
                and (not series or stamp > series[-1]["timestamp"])):
            series.append({"timestamp": stamp, **{key: metrics[key] for key in HISTORY_METRICS}})
        if host in grouped:
            coverage.append("REGISTRY_ALIASES_GROUPED")
        if host in conflicts:
            coverage.append("HISTORY_ORDER_INVALID")
        if len(series) < 2:
            coverage.append("HISTORY_INSUFFICIENT")
        if not series or any(p["memory_used_pct"] is None for p in series):
            coverage.append("MEMORY_HISTORY_INCOMPLETE")
        findings = _findings(state, metrics, series, thermal, now)
        points = _downsample(series)
        history_truncated = history_truncated or len(points) < len(series)
        hosts.append({"id": host, "label": host,
                      "platform": {"darwin": "macos", "linux": "linux"}.get(entry.get("platform"), "unknown"),
                      "state": state, "observed_at": stamp, "metrics": metrics,
                      "history": points, "findings": findings, "coverage": coverage})
    doc = {"schema": SCHEMA, "availability": "AVAILABLE" if all(h["state"] == "CURRENT" for h in hosts) else "PARTIAL",
           "generated_at": now, "window": window, "history_truncated": history_truncated,
           "admission_authoritative": False, "source": "fabric_host_observer", "hosts": hosts, "reason_codes": []}
    if len(json.dumps(doc, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_RESPONSE_BYTES:
        return unavailable_fleet(window, now, "RESPONSE_OVER_BUDGET")
    return doc


def _read_at(directory, name, limit, *, tail=False):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or (not tail and info.st_size > limit):
            raise ValueError("source file refused")
        skipped = max(0, info.st_size - limit) if tail else 0
        os.lseek(fd, skipped, os.SEEK_SET)
        remaining = info.st_size - skipped
        chunks = []
        while remaining:
            data = os.read(fd, min(65536, remaining))
            if not data:
                raise ValueError("source changed during read")
            chunks.append(data)
            remaining -= len(data)
        after = os.fstat(fd)
        if not tail and (info.st_size, info.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("source changed during read")
        content = b"".join(chunks)
        if skipped:
            content = content.partition(b"\n")[2]
        return content.decode("utf-8"), bool(skipped)
    finally:
        os.close(fd)


def _json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate source key")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite source")))


def read_fleet_health(fabric_root: Path, *, window="24h", now=None):
    """Read the already-running observer's files; no refresh or host effects.

    The trusted service installer supplies fabric_root. It is never a public
    request field. Same-descriptor, regular-file reads reject symlinks/FIFOs;
    a log tail is explicitly bounded and cannot claim unlimited retention.
    """
    now = time.time() if now is None else now
    _inputs(window, now)
    descriptors = []
    try:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        root = os.open(fabric_root, flags)
        descriptors.append(root)
        registry_text, _ = _read_at(root, "hosts.json", 256 * 1024)
        registry = _json(registry_text)
        entries, _ = _registered(registry)
        state = os.open("state", flags, dir_fd=root)
        descriptors.append(state)
        hosts = os.open("hosts", flags, dir_fd=state)
        descriptors.append(hosts)
        snapshots = {}
        for host in entries:
            try:
                text, _ = _read_at(hosts, host + ".json", 128 * 1024)
                snapshots[host] = _json(text)
            except (OSError, ValueError, UnicodeError):
                snapshots[host] = None
        try:
            log_text, truncated = _read_at(state, "host_pull.log", _WINDOW_HISTORY_BYTES[window], tail=True)
        except (OSError, ValueError, UnicodeError):
            log_text, truncated = "", False
        current_registry, _ = _read_at(root, "hosts.json", 256 * 1024)
        if current_registry != registry_text:
            return unavailable_fleet(window, now, "SOURCE_CHANGED")
        return compose_fleet_health(registry, snapshots, log_text, window=window,
                                    now=now, history_truncated=truncated)
    except (OSError, ValueError, UnicodeError, TypeError):
        return unavailable_fleet(window, now)
    finally:
        for fd in reversed(descriptors):
            os.close(fd)
