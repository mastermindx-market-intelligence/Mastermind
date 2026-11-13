"""Restart continuity for the incumbent router's admission window.

This is a bounded checkpoint of RateWindow and its provider observations, not an
independent quota ledger. It never grants entitlement or contacts a provider.
Only one serving router generation may own this file at a time.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import stat
import tempfile
import time

SCHEMA = "fabric.admission-window.v1"
MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 8192


def _number(value, low=0, high=10**12):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("invalid admission checkpoint number")
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError("invalid admission checkpoint number")
    return float(value)


def _identity(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        raise ValueError("invalid admission checkpoint identity")
    return value


def _cold_guard(policy, now, delay):
    for rid, rule in policy.resources.items():
        if rule.get("strict_output_reservation"):
            key = rule.get("key", rid)
            policy.recovery_until[key] = max(policy.recovery_until.get(key, 0), now + delay)


def restore(policy):
    now, wall = time.monotonic(), time.time()
    path = Path(policy.checkpoint_path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        # On first installation, recent consumption by the previous generation
        # is unknown. One complete sustained window must elapse before Kimi.
        _cold_guard(policy, now, 60)
        return
    except OSError:
        policy.persistence_error = "FABRIC_ADMISSION_CHECKPOINT_UNREADABLE"
        return
    try:
        try:
            metadata = os.fstat(fd)
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
                    or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1
                    or not 0 < metadata.st_size <= MAX_BYTES):
                raise ValueError("unsafe admission checkpoint")
            raw = bytearray()
            while len(raw) <= MAX_BYTES:
                chunk = os.read(fd, min(65536, MAX_BYTES + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
            after = os.fstat(fd)
            if (len(raw) != metadata.st_size or after.st_mtime_ns != metadata.st_mtime_ns
                    or after.st_ctime_ns != metadata.st_ctime_ns):
                raise ValueError("admission checkpoint changed")
        finally:
            os.close(fd)
        data = json.loads(raw)
        if data.get("schema") != SCHEMA or _number(data.get("saved_at")) > wall + 5:
            raise ValueError("invalid admission checkpoint epoch")
        samples, recovery, observed, capacity, cooldown = {}, {}, {}, {}, {}
        rows = data.get("samples", [])
        if not isinstance(rows, list) or len(rows) > MAX_ROWS:
            raise ValueError("invalid admission checkpoint samples")
        for resource, at, inp, out in rows:
            resource = _identity(resource)
            age = wall - _number(at)
            inp, out = _number(inp, high=1e9), _number(out, high=1e9)
            if age < -5:
                raise ValueError("future admission sample")
            if age < 60:
                samples.setdefault(resource, []).append((now - max(0, age), inp, out))
        holds = data.get("recovery", {})
        if not isinstance(holds, dict) or len(holds) > MAX_ROWS:
            raise ValueError("invalid recovery holds")
        for resource, until in holds.items():
            delay = _number(until) - wall
            if 0 < delay <= policy.uncertainty_s + 65:
                recovery[_identity(resource)] = now + delay
            elif delay > policy.uncertainty_s + 65:
                raise ValueError("invalid recovery deadline")
        pending = data.get("pending", [])
        if not isinstance(pending, list) or len(pending) > 128:
            raise ValueError("invalid pending admissions")
        for resource, started, inp, out in pending:
            resource, started = _identity(resource), _number(started)
            _number(inp, high=1e9); _number(out, high=1e9)
            if started > wall + 5:
                raise ValueError("future pending admission")
            until = now + max(0, started + policy.uncertainty_s - wall)
            recovery[resource] = max(recovery.get(resource, 0), until)
        lower = data.get("observed_limits", {})
        if not isinstance(lower, dict) or len(lower) > 1024:
            raise ValueError("invalid observed limits")
        for resource, fields in lower.items():
            observed[_identity(resource)] = {key: _number(value, 1, 1e9)
                for key, value in fields.items() if key in ("input_tpm", "output_tpm")}
        for rid, until in data.get("cooldown", {}).items():
            delay = _number(until) - wall
            if 0 < delay <= 1e9:
                cooldown[_identity(rid)] = now + delay
        probes = data.get("probe_required", list(data.get("cooldown", {})))
        if not isinstance(probes, list) or len(probes) > 1024:
            raise ValueError("invalid recovery probes")
        probes = {_identity(rid) for rid in probes}
        views = data.get("provider_capacity", {})
        if not isinstance(views, dict) or len(views) > 1024:
            raise ValueError("invalid provider capacity")
        for resource, dimensions in views.items():
            resource = _identity(resource)
            for dimension, view in dimensions.items():
                if dimension not in ("input", "output"):
                    raise ValueError("invalid provider dimension")
                age = wall - _number(view["at"])
                if age < -5:
                    raise ValueError("future provider observation")
                if age >= 60:
                    continue
                capacity.setdefault(resource, {})[dimension] = {
                    "at": now - max(0, age), "limit": _number(view["limit"], 1, 1e9),
                    "remaining": _number(view["remaining"], -1e9, 1e9),
                    "reported_remaining": _number(view["reported_remaining"], -1e9, 1e9),
                    "basis": "restored_provider_observation", "reserved": {}}
        # Commit only after the complete checkpoint has passed validation.
        for resource, rows in samples.items():
            policy.window._samples[resource] = policy.window._collections.deque(sorted(rows))
        policy.recovery_until.update(recovery)
        policy.observed_limits.update(observed)
        policy.provider_capacity.update(capacity)
        policy.route_state.cooldown_until.update(cooldown)
        for rid in probes:
            if rid in policy.routes:
                policy.route_state.consecutive_failures[rid] = max(1,
                    policy.route_state.consecutive_failures.get(rid, 0))
        for rid, rule in policy.resources.items():
            for field, value in observed.get(rule.get("key", rid), {}).items():
                if field in rule:
                    rule[field] = min(rule[field], value)
        policy.persistence_restored = True
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        # Corrupt state is not an empty/full allowance. Operator repair is needed.
        policy.persistence_error = "FABRIC_ADMISSION_CHECKPOINT_INVALID"


def encode(policy):
    """Capture one immutable snapshot on the admission owner's event loop."""
    now, wall = time.monotonic(), time.time()
    samples = [(resource, wall - (now - at), inp, out)
        for resource in list(policy.window._samples)
        for at, inp, out in policy.window._q(resource, now)]
    if len(samples) > MAX_ROWS:
        raise ValueError("admission checkpoint capacity exceeded")
    views = {resource: {dimension: {**{k: v for k, v in view.items() if k != "reserved"},
                        "at": wall - (now - view["at"])}
                for dimension, view in dimensions.items() if now - view["at"] < 60}
            for resource, dimensions in policy.provider_capacity.items()}
    data = {"schema": SCHEMA, "saved_at": wall, "samples": samples,
        "pending": [(a.resource, wall - (now - a.started), a.input_estimate, a.output_estimate)
                    for a in policy.active.values() if a.operation == "inference"],
        "probe_required": sorted(rid for rid, count in policy.route_state.consecutive_failures.items()
                                 if count > 0 and rid in policy.routes),
        "recovery": {resource: wall + until - now for resource, until in policy.recovery_until.items() if until > now},
        "observed_limits": policy.observed_limits, "provider_capacity": views,
        "cooldown": {rid: wall + until - now for rid, until in policy.route_state.cooldown_until.items() if until > now}}
    raw = json.dumps(data, separators=(",", ":"), allow_nan=False).encode()
    if len(raw) > MAX_BYTES:
        raise ValueError("admission checkpoint too large")
    return raw


def write(path, raw):
    """Persist immutable bytes; safe to run off-loop without reading policy."""
    path, tmp = Path(path), None
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".admission-", dir=path.parent)
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass


def save(policy):
    if policy.persistence_error:
        return False
    try:
        write(policy.checkpoint_path, encode(policy))
        return True
    except (OSError, ValueError, TypeError):
        policy.persistence_error = "FABRIC_ADMISSION_CHECKPOINT_WRITE_FAILED"
        return False
