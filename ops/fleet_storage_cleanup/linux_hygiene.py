#!/usr/bin/env python3
"""Linux peer of Mastermind's existing fleet storage sweeper.

The on-host hourly systemd user timer runs this low-impact pass even if ChatGPT
and the M2 SSH coordinator are absent. Worktree and /tmp cleanup is intentionally
REPORT-ONLY: active Fabric leases and human web-session attachments cannot be
proved from a directory age or a dead process. Actual worktree reclamation stays
with the existing canonical owner after exact per-worktree proof.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import time

GIB = 1024 ** 3
STATE = Path.home() / ".local/state/mastermind/storage-cleanup"
LEDGER = "linux-hygiene.jsonl"
HOLD = "linux-cache-effect-unverified"


def volume(path: Path) -> dict:
    """Observe the actual resolved mount; absent/broken volumes are not healthy."""
    try:
        if not path.exists():
            return {"path": str(path), "state": "UNAVAILABLE"}
        resolved = path.resolve(strict=True)
        v = os.statvfs(resolved)
        total = v.f_blocks * v.f_frsize
        free = v.f_bavail * v.f_frsize
        return {
            "path": str(path), "resolved": str(resolved), "state": "OK",
            "total_bytes": total, "available_bytes": free,
            "inodes_total": v.f_files, "inodes_available": v.f_favail,
            "total_gib": round(total / GIB, 2),
            "free_gib": round(free / GIB, 2),
            "free_fraction": round(free / total, 4) if total else None,
            "inodes_free_fraction": round(v.f_favail / v.f_files, 4) if v.f_files else None,
            "device": os.stat(resolved).st_dev,
        }
    except (OSError, RuntimeError, ValueError) as exc:
        return {"path": str(path), "state": "UNVERIFIED",
                "error": type(exc).__name__}


def memory(path: Path = Path("/proc/meminfo")) -> dict:
    try:
        values = {}
        for line in path.read_text().splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                parts = value.split()
                if parts and parts[0].isdigit():
                    values[key] = int(parts[0])
        total = values.get("MemTotal", 0)
        avail = values.get("MemAvailable")
        if not total or avail is None or avail > total:
            return {"state": "UNVERIFIED", "reason": "meminfo_missing_or_invalid"}
        swap = values.get("SwapTotal", 0)
        return {
            "state": "OK", "total_gib": round(total / 1024**2, 2),
            "available_gib": round(avail / 1024**2, 2),
            "available_fraction": round(avail / total, 4),
            "swap_used_gib": round((swap - values.get("SwapFree", swap)) / 1024**2, 2),
            "pressure": "CRITICAL" if avail / total < 0.12 else
                        "WARNING" if avail / total < 0.22 else "CALM",
        }
    except OSError as exc:
        return {"state": "UNVERIFIED", "error": type(exc).__name__}


def classify(total_gib: float, free_gib: float, inode_fraction: float | None,
             configured_floor_gib: float | None = None) -> str:
    """Operational sweep intensity. Not a substitute for Fabric admission."""
    if total_gib <= 0 or free_gib < 0 or free_gib > total_gib:
        return "UNVERIFIED"
    if inode_fraction is not None and not 0 <= inode_fraction <= 1:
        return "UNVERIFIED"
    critical = max(60, total_gib * 0.14,
                   configured_floor_gib or 0)
    warn = max(120, total_gib * 0.22,
               (configured_floor_gib + 15) if configured_floor_gib else 0)
    if free_gib < critical or (inode_fraction is not None and inode_fraction < 0.02):
        return "CRITICAL"
    if free_gib < warn or (inode_fraction is not None and inode_fraction < 0.05):
        return "CAUTION"
    return "CALM"


def reserve(root: Path) -> dict:
    """Optional current owner-supplied reserve; never invent one or lower a floor."""
    config = root / ".config/mastermind/fabric-storage-reserve.json"
    try:
        obj = json.loads(config.read_text())
        value = obj.get("internal_floor_gib")
        if type(value) not in (float, int) or not 0 < value < 1e6:
            raise ValueError("invalid_floor")
        return {"state": "CONFIGURED", "floor_gib": float(value)}
    except FileNotFoundError:
        return {"state": "UNVERIFIED", "reason": "no_local_fabric_floor"}
    except (ValueError, OSError, TypeError, AttributeError) as exc:
        return {"state": "UNVERIFIED", "reason": type(exc).__name__}


def candidates(root: Path, min_days: int = 3, limit: int = 20) -> dict:
    """Shallow, never-follow-symlink observations. NEVER deletion candidates by fiat."""
    worktrees = root / "lanes/wt"
    if not worktrees.is_dir() or worktrees.is_symlink():
        return {"state": "UNVERIFIED", "reason": "worktree_root_missing_or_symlink"}
    output = []
    try:
        for item in worktrees.iterdir():
            if item.is_symlink() or not item.is_dir():
                continue
            age = (time.time() - item.stat(follow_symlinks=False).st_mtime) / 86400
            if age >= min_days:
                output.append({"name": item.name, "directory_mtime_age_days": round(age, 1)})
        output.sort(key=lambda x: -x["directory_mtime_age_days"])
        return {"state": "OBSERVED_ONLY", "count_aged": len(output),
                "examples": output[:limit],
                "warning": "not deletion proof: requires Git state, PR, human attachment and Fabric lease"}
    except OSError as exc:
        return {"state": "UNVERIFIED", "reason": type(exc).__name__}


def package_command(argv: bytes) -> bool:
    """Conservatively recognize every manager invocation, including flag variants."""
    tokens = [part.decode("utf-8", "replace").lower()
              for part in argv.split(b"\x00") if part]
    if not tokens:
        return False
    executable = os.path.basename(tokens[0])
    if (executable in {"pip", "pip3", "pipx", "uv", "npm", "npm.cmd",
                       "pnpm", "yarn", "npx", "corepack"}
            or executable.startswith("pip3.")):
        return True
    if any(token.endswith(("/npm-cli.js", "/pnpm.cjs", "/yarn.js",
                             "/pip/__main__.py")) for token in tokens):
        return True
    return any(token == "-m" and index + 1 < len(tokens)
               and (tokens[index + 1] == "pip"
                    or tokens[index + 1].startswith("pip."))
               for index, token in enumerate(tokens))


def package_busy() -> bool:
    """Unreadable/truncated process snapshots and ANY cache writer fail closed."""
    try:
        for proc in Path("/proc").iterdir():
            if not proc.name.isdigit() or int(proc.name) == os.getpid():
                continue
            try:
                with (proc / "cmdline").open("rb") as source:
                    raw = source.read(4097)
            except FileNotFoundError:
                continue  # pid exited during the census
            except OSError:
                return True  # potentially active writer; no guessing
            if len(raw) > 4096 or package_command(raw):
                return True
    except OSError:
        return True
    return False


def trusted_cache_target(root: Path, cache: Path) -> bool:
    """Approved same-user path only; no symlinks or writable directory parents."""
    try:
        root, cache = root.absolute(), cache.absolute()
        parts = cache.relative_to(root).parts
        if not parts or root.is_symlink() or root.resolve(strict=True) != root:
            return False
        for path in (root, *(root.joinpath(*parts[:i]) for i in range(1, len(parts)+1))):
            info = path.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)):
                return False
        return cache.resolve(strict=True) == cache
    except (OSError, ValueError, RuntimeError):
        return False


def cache_redirected(name: str) -> bool:
    """Fail closed on ambient manager config; CLI also pins the exact path."""
    overrides = {"XDG_CACHE_HOME"}
    if name == "pip":
        overrides |= {"PIP_CACHE_DIR", "PIP_CONFIG_FILE"}
    elif name == "uv":
        overrides |= {"UV_CACHE_DIR", "UV_CONFIG_FILE", "UV_NO_CACHE"}
    else:
        overrides |= {"npm_config_cache", "NPM_CONFIG_CACHE",
                      "npm_config_userconfig", "NPM_CONFIG_USERCONFIG",
                      "npm_config_globalconfig", "NPM_CONFIG_GLOBALCONFIG"}
    return any(key in os.environ for key in overrides)


def effect_volume_pair_ok(root_volume: dict, cache_volume: dict) -> bool:
    """Require byte/inode-exact observations on one stable filesystem.

    A successful package-manager exit cannot identify which process caused a
    free-space delta; observations are never an attributable reclaimed-byte
    counter. Reject missing precision and separate mounts before any effect.
    """
    for snapshot in (root_volume, cache_volume):
        if snapshot.get("state") != "OK":
            return False
        for field in ("device", "total_bytes", "available_bytes",
                      "inodes_total", "inodes_available"):
            if type(snapshot.get(field)) is not int or snapshot[field] < 0:
                return False
        if (snapshot["total_bytes"] <= 0 or
                snapshot["available_bytes"] > snapshot["total_bytes"] or
                snapshot["inodes_available"] > snapshot["inodes_total"]):
            return False
    return root_volume["device"] == cache_volume["device"]


def cache_cleanup(root: Path, state: Path, mode: str) -> list[dict]:
    """Only package-manager cache APIs; no arbitrary rm, /tmp or Git pruning."""
    if mode == "CALM":
        return [{"state": "SKIPPED_CALM"}]
    if (state / HOLD).exists():
        return [{"state": "HELD_EFFECT_UNVERIFIED"}]
    if package_busy():
        return [{"state": "SKIPPED_PACKAGE_ACTIVITY"}]
    pip_cache = root / ".cache/pip"
    uv_cache = root / ".cache/uv"
    npm_root = root / ".npm"
    plans = [
        ("pip", pip_cache, [sys.executable, "-m", "pip", "--isolated",
                           "--cache-dir", str(pip_cache), "cache", "purge"]),
        ("uv", uv_cache, ["uv", "--cache-dir", str(uv_cache), "cache", "clean"]),
    ]
    if mode == "CRITICAL":
        plans.append(("npm", npm_root / "_cacache",
                      ["npm", "--cache", str(npm_root), "cache", "clean", "--force"]))
    results = []
    for name, cache, argv in plans:
        if cache_redirected(name):
            results.append({"cache": name, "state": "SKIPPED_CUSTOM_CACHE_PATH"})
            continue
        if not trusted_cache_target(root, cache):
            results.append({"cache": name, "state": "SKIPPED_UNTRUSTED_CACHE_PATH"})
            continue
        if not shutil.which(argv[0]):
            results.append({"cache": name, "state": "SKIPPED_UNAVAILABLE"})
            continue
        # A different writer can start between consecutive cache purges.
        # Recheck before EACH destructive manager API, not only at entry.
        if package_busy():
            results.append({"cache": name, "state": "SKIPPED_PACKAGE_ACTIVITY"})
            break
        # Capture exact values on the same filesystem before each distinct
        # manager effect; a historic/rounded root snapshot is not sufficient.
        before_root, before_cache = volume(Path("/")), volume(cache)
        if not effect_volume_pair_ok(before_root, before_cache):
            results.append({"cache": name, "state": "SKIPPED_UNVERIFIED_EFFECT_VOLUME"})
            break
        marker = state / HOLD
        effect_id = f"{time.time_ns()}-{os.getpid()}"
        try:
            # Fail closed BEFORE entering the destructive package-manager API.
            # A crash or interrupted parent then leaves a durable hold which
            # refuses unattended retries until the exact effect is reconciled.
            with marker.open("x") as intent:
                intent.write(f"{time.time()}: PRE_EFFECT cache={name}\n")
                intent.write(json.dumps({"schema": "mastermind.cache_effect_preimage.v1",
                                         "cache": name, "effect_id": effect_id,
                                         "root": before_root, "target": before_cache},
                                        sort_keys=True) + "\n")
                intent.flush()
                os.fsync(intent.fileno())
            directory_fd = os.open(state, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            results.append({"cache": name, "state": "MARKER_UNAVAILABLE",
                            "error": type(exc).__name__})
            break
        started = time.monotonic()
        try:
            proc = subprocess.run(argv, cwd=str(root), capture_output=True,
                                  text=True, timeout=90)
        except (subprocess.TimeoutExpired, OSError) as exc:
            # The PRE_EFFECT hold remains. A timeout is not proof the child
            # or its descendants performed no changes.
            results.append({"cache": name, "state": "EFFECT_UNVERIFIED",
                            "error": type(exc).__name__})
            break
        if proc.returncode:
            # Nonzero package-manager exit may include partial cache deletion.
            results.append({"cache": name, "state": "EFFECT_UNVERIFIED",
                            "exit_code": proc.returncode,
                            "duration_sec": round(time.monotonic() - started, 2),
                            "error_class": "MANAGER_EXIT_NONZERO",
                            "stderr_redacted": bool(proc.stderr)})
            break
        after_root, after_cache = volume(Path("/")), volume(cache)
        if (not effect_volume_pair_ok(after_root, after_cache)
                or before_root["device"] != after_root["device"]
                or before_cache["device"] != after_cache["device"]
                or not trusted_cache_target(root, cache)):
            # Process success without exact stable postimage is effect-unknown.
            # Preserve the durable hold; never infer completion from exit=0.
            results.append({"cache": name, "state": "EFFECT_UNVERIFIED",
                            "reason": "post_effect_volume_or_target_unverified",
                            "exit_code": 0})
            break
        measurement = {
            "device": before_root["device"],
            "before_available_bytes": before_root["available_bytes"],
            "after_available_bytes": after_root["available_bytes"],
            "before_free_inodes": before_root["inodes_available"],
            "after_free_inodes": after_root["inodes_available"],
            "observed_available_delta_bytes":
                after_root["available_bytes"] - before_root["available_bytes"],
            "observed_free_inodes_delta":
                after_root["inodes_available"] - before_root["inodes_available"],
            "attributable_reclaimed_bytes": 0,
            "reclaim_attribution": "NOT_ESTABLISHED_BY_MANAGER",
        }
        # Durable settlement in the ORIGINAL JSONL owner must precede release
        # of PRE_EFFECT. Otherwise a crash between unlink and the run's final
        # heartbeat silently loses evidence that the manager had an effect.
        settlement = {
            "schema": "mastermind.cache_effect_settlement.v1",
            "effect_id": effect_id, "epoch": time.time(),
            "host": socket.gethostname(), "cache": name,
            "state": "POST_EFFECT_VERIFIED", "exit_code": 0,
            **measurement,
            "duration_sec": round(time.monotonic() - started, 2),
        }
        if not append_receipt(state, settlement):
            results.append({"cache": name, "state": "EFFECT_UNVERIFIED",
                            "reason": "settlement_receipt_unavailable"})
            break  # preserve PRE_EFFECT for original-owner reconciliation
        try:
            marker.unlink()
        except OSError as exc:
            # Success without a verified hold clear is NOT a healthy tick.
            results.append({"cache": name, "state": "EFFECT_UNVERIFIED",
                            "error": type(exc).__name__})
            break
        results.append({"cache": name, "state": "OK",
                        "exit_code": 0, **measurement,
                        "duration_sec": round(time.monotonic() - started, 2),
                        "stderr_tail": ""})
    return results


def run(state: Path, root: Path, apply_safe_caches: bool) -> dict:
    before = volume(Path("/"))
    lanes = volume(root / "lanes")
    mem = memory()
    configured = reserve(root)
    floor = configured.get("floor_gib")
    mode = classify(before["total_gib"], before["free_gib"],
                    before["inodes_free_fraction"], floor) if before.get("state") == "OK" else "UNVERIFIED"
    worktrees = candidates(root, 1 if mode == "CRITICAL" else 3)
    mandatory_ok = (mode != "UNVERIFIED" and mem.get("state") == "OK"
                    and lanes.get("state") == "OK"
                    and worktrees.get("state") == "OBSERVED_ONLY"
                    and configured.get("state") == "CONFIGURED"
                    and before.get("inodes_free_fraction") is not None
                    and type(before.get("available_bytes")) is int
                    and type(before.get("inodes_available")) is int
                    and type(lanes.get("available_bytes")) is int
                    and type(lanes.get("inodes_available")) is int)
    result = {"schema": "mastermind.fleet_linux_hygiene.v1",
              "epoch": time.time(), "host": socket.gethostname(),
              "mode": mode, "root": before, "lanes": lanes, "memory": mem,
              "fabric_reserve": configured,
              "fabric_admission": "UNVERIFIED",  # incumbent picker alone admits workers
              "worktrees": worktrees, "cleanup": []}
    if apply_safe_caches and mode in ("CAUTION", "CRITICAL") and mandatory_ok:
        result["cleanup"] = cache_cleanup(root, state, mode)
    elif apply_safe_caches and not mandatory_ok:
        result["cleanup"] = [{"state": "SKIPPED_MANDATORY_OBSERVATION_UNVERIFIED"}]
    else:
        result["cleanup"] = [{"state": "REPORT_ONLY" if not apply_safe_caches else "NO_PRESSURE"}]
    result["root_after"] = volume(Path("/"))
    result["finished_epoch"] = time.time()
    after = result["root_after"]
    # Root drift can be observed exactly but never attributed to this cleaner
    # without distinct, trusted manager-specific byte evidence.
    result["observed_root_available_delta_bytes"] = (
        after["available_bytes"] - before["available_bytes"]
        if before.get("state") == after.get("state") == "OK"
        and before.get("device") == after.get("device")
        and type(before.get("available_bytes")) is int
        and type(after.get("available_bytes")) is int else None)
    result["attributable_reclaimed_bytes"] = 0
    result["reclaim_attribution"] = "NO_VERIFIED_MANAGER_SPECIFIC_BYTE_EVIDENCE"
    result["degraded"] = (not mandatory_ok or after.get("state") != "OK"
                          or after.get("inodes_free_fraction") is None
                          or (before.get("state") == "OK" and after.get("device") != before.get("device"))
                          or any(x.get("state") in ("FAILED", "EFFECT_UNVERIFIED",
                                                   "HELD_EFFECT_UNVERIFIED",
                                                   "MARKER_UNAVAILABLE",
                                                   "SKIPPED_UNVERIFIED_EFFECT_VOLUME",
                                                   "SKIPPED_MANDATORY_OBSERVATION_UNVERIFIED")
                                 for x in result["cleanup"]))
    return result


def append_receipt(state: Path, report: dict) -> bool:
    """One O_APPEND write + fsync; never follow a replaced ledger symlink."""
    row = (json.dumps(report, sort_keys=True) + "\n").encode("utf-8")
    if len(row) > 32768:
        return False
    fd = None
    try:
        fd = os.open(state / LEDGER, os.O_APPEND | os.O_CREAT | os.O_WRONLY |
                     os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
        if os.write(fd, row) != len(row):
            return False
        os.fsync(fd)
        # The first successful effect may create the ledger's directory entry.
        # Persist that name before declaring PRE_EFFECT safely settled.
        directory_fd = os.open(state, os.O_RDONLY | os.O_DIRECTORY |
                               os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return True
    except OSError:
        return False
    finally:
        if fd is not None:
            os.close(fd)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply-safe-caches", action="store_true")
    parser.add_argument("--state-dir", type=Path, default=STATE)
    args = parser.parse_args(argv)
    state = args.state_dir.expanduser()
    if state.is_symlink():
        print(json.dumps({"state": "REFUSED_SYMLINK_STATE"}))
        return 2
    state.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(state / "linux-hygiene.lock",
                     os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    except OSError as exc:
        print(json.dumps({"state": "LOCK_UNAVAILABLE", "error": type(exc).__name__}),
              file=sys.stderr)
        return 2
    with os.fdopen(fd, "a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            report = {"schema": "mastermind.fleet_linux_hygiene.v1",
                      "epoch": time.time(), "host": socket.gethostname(),
                      "state": "DEFERRED_ALREADY_RUNNING", "degraded": True}
            recorded = append_receipt(state, report)
            print(json.dumps(report, sort_keys=True),
                  file=sys.stdout if recorded else sys.stderr)
            # A deferred run is NOT success; the original hourly timer survives.
            return 75
        try:
            report = run(state, Path.home(), args.apply_safe_caches)
        except Exception as exc:
            report = {"schema": "mastermind.fleet_linux_hygiene.v1",
                      "epoch": time.time(), "host": socket.gethostname(),
                      "state": "FAILED", "error": type(exc).__name__}
        recorded = append_receipt(state, report)
        print(json.dumps(report, sort_keys=True),
              file=sys.stdout if recorded else sys.stderr)
        # A missing receipt, failure or degraded observation can never be green.
        return 1 if (not recorded or report.get("state") == "FAILED"
                     or report.get("degraded")) else 0


if __name__ == "__main__":
    raise SystemExit(main())
