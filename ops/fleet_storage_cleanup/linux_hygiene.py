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


def package_busy() -> bool:
    """If another package command is visible, do not modify shared caches."""
    try:
        for proc in Path("/proc").iterdir():
            if not proc.name.isdigit() or int(proc.name) == os.getpid():
                continue
            try:
                cmd = (proc / "cmdline").read_bytes()[:500].replace(b"\\x00", b" ").lower()
            except (OSError, PermissionError):
                continue
            if any(key in cmd for key in
                   (b"pip install", b"pip3 install", b"uv pip", b"uv sync",
                    b"npm install", b"npm ci", b"pnpm install", b"yarn install")):
                return True
    except OSError:
        return True
    return False


def cache_cleanup(root: Path, state: Path, mode: str) -> list[dict]:
    """Only package-manager cache APIs; no arbitrary rm, /tmp or Git pruning."""
    if mode == "CALM":
        return [{"state": "SKIPPED_CALM"}]
    if (state / HOLD).exists():
        return [{"state": "HELD_EFFECT_UNVERIFIED"}]
    if package_busy():
        return [{"state": "SKIPPED_PACKAGE_ACTIVITY"}]
    plans = [
        ("pip", root / ".cache/pip", [sys.executable, "-m", "pip", "cache", "purge"],
         ("PIP_CACHE_DIR",)),
        ("uv", root / ".cache/uv", ["uv", "cache", "clean"], ("UV_CACHE_DIR",)),
    ]
    if mode == "CRITICAL":
        plans.append(("npm", root / ".npm/_cacache",
                      ["npm", "cache", "clean", "--force"], ("npm_config_cache",)))
    results = []
    for name, cache, argv, overrides in plans:
        if any(os.environ.get(key) for key in overrides):
            results.append({"cache": name, "state": "SKIPPED_CUSTOM_CACHE_PATH"})
            continue
        if not cache.is_dir() or cache.is_symlink() or not shutil.which(argv[0]):
            results.append({"cache": name, "state": "SKIPPED_UNAVAILABLE"})
            continue
        try:
            started = time.monotonic()
            proc = subprocess.run(argv, cwd=str(root), capture_output=True,
                                  text=True, timeout=150)
            results.append({"cache": name, "state": "OK" if proc.returncode == 0 else "FAILED",
                            "exit_code": proc.returncode,
                            "duration_sec": round(time.monotonic() - started, 2),
                            "stderr_tail": proc.stderr[-160:] if proc.returncode else ""})
        except (subprocess.TimeoutExpired, OSError) as exc:
            # A timed-out subprocess is not proof its descendants had no effects.
            (state / HOLD).write_text(f"{time.time()}: {name}: {type(exc).__name__}\\n")
            results.append({"cache": name, "state": "EFFECT_UNVERIFIED",
                            "error": type(exc).__name__})
            break
    return results


def run(state: Path, root: Path, apply_safe_caches: bool) -> dict:
    before = volume(Path("/"))
    lanes = volume(root / "lanes")
    mem = memory()
    configured = reserve(root)
    floor = configured.get("floor_gib")
    mode = classify(before["total_gib"], before["free_gib"],
                    before["inodes_free_fraction"], floor) if before.get("state") == "OK" else "UNVERIFIED"
    result = {"schema": "mastermind.fleet_linux_hygiene.v1",
              "epoch": time.time(), "host": socket.gethostname(),
              "mode": mode, "root": before, "lanes": lanes, "memory": mem,
              "fabric_reserve": configured,
              "worktrees": candidates(root, 1 if mode == "CRITICAL" else 3),
              "cleanup": []}
    if apply_safe_caches and mode in ("CAUTION", "CRITICAL"):
        result["cleanup"] = cache_cleanup(root, state, mode)
    else:
        result["cleanup"] = [{"state": "REPORT_ONLY" if not apply_safe_caches else "NO_PRESSURE"}]
    result["root_after"] = volume(Path("/"))
    result["finished_epoch"] = time.time()
    result["degraded"] = (mode == "UNVERIFIED" or mem.get("state") != "OK" or
                          any(x.get("state") in ("FAILED", "EFFECT_UNVERIFIED",
                                                 "HELD_EFFECT_UNVERIFIED")
                              for x in result["cleanup"]))
    return result


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
    with (state / "linux-hygiene.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({"state": "DEFERRED_ALREADY_RUNNING"}))
            return 0
        try:
            report = run(state, Path.home(), args.apply_safe_caches)
        except Exception as exc:
            # Preserve an explicit failed heartbeat, not a false green.
            report = {"schema": "mastermind.fleet_linux_hygiene.v1",
                      "epoch": time.time(), "host": socket.gethostname(),
                      "state": "FAILED", "error": type(exc).__name__}
        with (state / LEDGER).open("a") as ledger:
            ledger.write(json.dumps(report, sort_keys=True) + "\n")
        print(json.dumps(report, sort_keys=True))
        return 1 if report.get("state") == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
