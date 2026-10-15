"""Closed Fleet diagnostics DTO shared by its producer and workspace edge.

This is a presentation contract, not a Host Capacity or agent identity schema.
"""
from __future__ import annotations

import json
import math
import re

FLEET_SCHEMA = "mastermind.fleet_health.v1"
FLEET_WINDOWS = {"1h": 3600, "24h": 86400, "7d": 604800, "30d": 2592000}
FLEET_MAX_RESPONSE_BYTES = 1_500_000
FLEET_MAX_AGE = 180
METRIC_KEYS = frozenset({"cpu_busy_pct", "load1", "load5", "logical_cpus",
    "memory_available_bytes", "memory_total_bytes", "memory_used_pct", "swap_used_bytes",
    "cpu_temp_c", "nvme_temp_c", "fan_rpm", "disk_free_bytes", "fabric_active_lanes",
    "process_lane_candidates", "thermal_advisory_c"})
HISTORY_KEYS = frozenset({"cpu_temp_c", "cpu_busy_pct", "load1", "memory_used_pct", "fabric_active_lanes"})
_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,79}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}\Z")


def fleet_selection(value):
    if (type(value) is not dict or set(value) != {"window"}
            or type(value["window"]) is not str or value["window"] not in FLEET_WINDOWS):
        raise ValueError("invalid_input")
    return dict(value)


def _keys(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        raise ValueError("Fleet response invalid")


def _number(value, low=0, high=2 ** 53 - 1, *, nullable=True, integer=False):
    if value is None and nullable:
        return
    if type(value) not in (int, float):
        raise ValueError("Fleet response invalid")
    try:
        valid = math.isfinite(value) and low <= value <= high and (not integer or int(value) == value)
    except (OverflowError, ValueError):
        valid = False
    if not valid:
        raise ValueError("Fleet response invalid")


def _text(value, limit):
    if type(value) is not str or not 1 <= len(value) <= limit:
        raise ValueError("Fleet response invalid")


def _codes(values, limit):
    if (type(values) is not list or len(values) > limit
            or any(type(v) is not str or not _CODE.fullmatch(v) for v in values)
            or len(set(values)) != len(values)):
        raise ValueError("Fleet response invalid")


def _metric(key, value):
    high = 100 if key in ("cpu_busy_pct", "memory_used_pct") else (
        150 if key in ("cpu_temp_c", "nvme_temp_c", "thermal_advisory_c") else 2 ** 53 - 1)
    _number(value, 1 if key == "logical_cpus" else 0, high,
            integer=key in ("logical_cpus", "fabric_active_lanes", "process_lane_candidates"))


def validate_fleet_document(value, *, expected_window):
    """Return detached validated public bytes, or refuse before disclosure."""
    fleet_selection({"window": expected_window})
    _keys(value, {"schema", "availability", "generated_at", "window", "history_truncated",
                  "admission_authoritative", "source", "hosts", "reason_codes"})
    if (value["schema"] != FLEET_SCHEMA or value["window"] != expected_window
            or value["source"] != "fabric_host_observer" or value["admission_authoritative"] is not False
            or type(value["history_truncated"]) is not bool
            or value["availability"] not in ("AVAILABLE", "PARTIAL", "UNAVAILABLE")):
        raise ValueError("Fleet response invalid")
    now = value["generated_at"]
    _number(now, 1, nullable=False)
    _codes(value["reason_codes"], 16)
    hosts = value["hosts"]
    if type(hosts) is not list or len(hosts) > 32:
        raise ValueError("Fleet response invalid")
    if value["availability"] == "UNAVAILABLE":
        if hosts or not value["reason_codes"]:
            raise ValueError("Fleet response invalid")
    elif not hosts or value["reason_codes"]:
        raise ValueError("Fleet response invalid")
    ids = set()
    for host in hosts:
        _keys(host, {"id", "label", "platform", "state", "observed_at", "metrics", "history", "findings", "coverage"})
        if type(host["id"]) is not str or not _ID.fullmatch(host["id"]) or host["id"] in ids:
            raise ValueError("Fleet response invalid")
        ids.add(host["id"])
        _text(host["label"], 100)
        if host["platform"] not in ("macos", "linux", "unknown") or host["state"] not in ("CURRENT", "STALE", "OFFLINE", "UNKNOWN"):
            raise ValueError("Fleet response invalid")
        stamp = host["observed_at"]
        _number(stamp, 1, now)
        if host["state"] in ("CURRENT", "STALE", "OFFLINE") and stamp is None:
            raise ValueError("Fleet response invalid")
        if host["state"] == "CURRENT" and now - stamp > FLEET_MAX_AGE:
            raise ValueError("Fleet response invalid")
        if host["state"] == "STALE" and now - stamp <= FLEET_MAX_AGE:
            raise ValueError("Fleet response invalid")
        metrics = host["metrics"]
        _keys(metrics, METRIC_KEYS)
        for key, measurement in metrics.items():
            _metric(key, measurement)
        if host["state"] in ("OFFLINE", "UNKNOWN") and any(v is not None for v in metrics.values()):
            raise ValueError("Fleet response invalid")
        total, available, used = (metrics[k] for k in ("memory_total_bytes", "memory_available_bytes", "memory_used_pct"))
        if total is not None and available is not None:
            if total <= 0 or available > total or (used is not None and abs(used - 100 * (1 - available / total)) > .1):
                raise ValueError("Fleet response invalid")
        _codes(host["coverage"], 16)
        history = host["history"]
        if type(history) is not list or len(history) > 360:
            raise ValueError("Fleet response invalid")
        previous = 0
        for point in history:
            _keys(point, HISTORY_KEYS | {"timestamp", "gaps"})
            _number(point["timestamp"], max(1, now - FLEET_WINDOWS[expected_window]), now, nullable=False)
            if point["timestamp"] <= previous:
                raise ValueError("Fleet response invalid")
            previous = point["timestamp"]
            for key in HISTORY_KEYS:
                _metric(key, point[key])
            gaps = point["gaps"]
            if (type(gaps) is not list or len(gaps) > 5
                    or any(type(k) is not str or k not in HISTORY_KEYS for k in gaps)
                    or len(set(gaps)) != len(gaps)):
                raise ValueError("Fleet response invalid")
        findings = host["findings"]
        if type(findings) is not list or len(findings) > 12:
            raise ValueError("Fleet response invalid")
        for finding in findings:
            _keys(finding, {"code", "severity", "category", "summary", "detail", "duration_seconds"})
            _codes([finding["code"]], 1)
            if finding["severity"] not in ("info", "warning", "critical") or finding["category"] not in ("coverage", "performance", "hardware"):
                raise ValueError("Fleet response invalid")
            _text(finding["summary"], 160)
            _text(finding["detail"], 800)
            _number(finding["duration_seconds"])
    if hosts and (value["availability"] == "AVAILABLE") != all(h["state"] == "CURRENT" for h in hosts):
        raise ValueError("Fleet response invalid")
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > FLEET_MAX_RESPONSE_BYTES:
        raise ValueError("Fleet response over budget")
    return json.loads(encoded)
