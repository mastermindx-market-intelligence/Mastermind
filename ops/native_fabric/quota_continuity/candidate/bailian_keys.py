#!/usr/bin/env python3
"""Bailian Token-Plan key picker (library + CLI).

Reads names and values from ~/.bailian/config.json (mode 600).
Key values stay inside this helper and the selected Codex child's environment.
The former `env <name>` stdout interface is retired in this native generation;
it fails without reading a credential. Account-name/status output is unchanged.

Usage:
  bailian_keys.py pick
  bailian_keys.py check-key <name>
  bailian_keys.py exec-codex <name> -- <codex exec arguments...>
  bailian_keys.py release <name> <pid>
  bailian_keys.py cooldown <name> <seconds> <reason>
  bailian_keys.py status
  bailian_keys.py total_cap
  bailian_keys.py next_usable_in
  bailian_keys.py model <requested>
  bailian_keys.py seconds_until_offpeak
"""
from __future__ import annotations

import fcntl
import json
import math
import os
import re
import stat
import sys
import time
from datetime import datetime
from typing import Any, Dict, IO, List, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
POLICY_PATH = os.path.join(HERE, "bailian_policy.json")
CONFIG_PATH = os.path.expanduser("~/.bailian/config.json")
SLOTS_ROOT = os.path.join(HERE, "slots", "bailian")
LOCK_PATH = os.path.join(SLOTS_ROOT, ".lock")


def _die(msg: str, rc: int = 2) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(rc)


def load_policy() -> Dict[str, Any]:
    with open(POLICY_PATH, encoding="utf-8") as fh:
        return json.load(fh)


# The policy's `offpeak_window` object is the single source of truth for the
# discounted window. A legacy `offpeak` / `_legacy_*` block is consulted only when
# `offpeak_window` is absent, so replaced fields can never silently move the cap
# or the model swap.
DEFAULT_OFFPEAK_START = "22:00"
DEFAULT_OFFPEAK_END = "08:00"
DEFAULT_OFFPEAK_TZ = "Asia/Shanghai"
# Model selection is independent of the discount/capacity window.
MINUTES_PER_DAY = 24 * 60


def _parse_hhmm(s: Any, fallback: str) -> int:
    """'HH:MM'[:SS] as minutes since midnight; bad input falls back to `fallback`."""
    try:
        h_raw, _, m_raw = str(s).strip().partition(":")
        hour, minute = int(h_raw), int(m_raw or 0)
    except (TypeError, ValueError):
        hour = minute = -1
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        h_raw, _, m_raw = fallback.strip().partition(":")
        hour, minute = int(h_raw), int(m_raw or 0)
    return hour * 60 + minute


def _now_in_tz(tz_name: str) -> datetime:
    if ZoneInfo is None:
        return datetime.now()
    return datetime.now(ZoneInfo(tz_name))


def _as_tz(dt: datetime, tz_name: str) -> datetime:
    """Move a clock reading into the window's tz (naive input is assumed local)."""
    if ZoneInfo is None:
        return dt
    tz = ZoneInfo(tz_name)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def _minutes_of_day(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


def offpeak_window(policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Resolved off-peak window: display HH:MM strings, tz, and minute offsets."""
    pol = load_policy() if policy is None else policy
    win = pol.get("offpeak_window")
    if not isinstance(win, dict):
        win = pol.get("_legacy_offpeak_window")
    if not isinstance(win, dict):
        win = pol.get("offpeak")
    if not isinstance(win, dict):
        win = {}
    start = str(win.get("start") or DEFAULT_OFFPEAK_START)
    end = str(win.get("end") or DEFAULT_OFFPEAK_END)
    tz_name = str(win.get("tz") or win.get("timezone") or DEFAULT_OFFPEAK_TZ)
    return {
        "start": start[:5],
        "end": end[:5],
        "tz": tz_name,
        "start_min": _parse_hhmm(start, DEFAULT_OFFPEAK_START),
        "end_min": _parse_hhmm(end, DEFAULT_OFFPEAK_END),
    }


def discounted_models(policy: Optional[Dict[str, Any]] = None) -> List[str]:
    pol = load_policy() if policy is None else policy
    models = pol.get("discounted_models")
    if not isinstance(models, list):
        return []
    return [str(m).strip() for m in models if str(m).strip()]


def offpeak_default_model(policy: Optional[Dict[str, Any]] = None) -> str:
    pol = load_policy() if policy is None else policy
    return str(pol.get("offpeak_default_model") or "").strip()


def is_offpeak(now: Optional[datetime] = None) -> bool:
    """True inside `offpeak_window`, which may cross midnight (22:00 -> 08:00).

    Half-open [start, end) at minute precision: 22:00 is in, 08:00 is out.
    VERIFY the window against Alibaba's published schedule.
    """
    win = offpeak_window()
    minute = _minutes_of_day(_as_tz(now or _now_in_tz(win["tz"]), win["tz"]))
    start, end = win["start_min"], win["end_min"]
    if start == end:
        return False  # degenerate window: assume no discount, stay on the tight cap
    if start < end:
        return start <= minute < end
    return minute >= start or minute < end  # window crosses midnight


def current_per_key_cap(now: Optional[datetime] = None) -> int:
    """`per_key_cap` inside the off-peak window, `onpeak_per_key_cap` outside."""
    pol = load_policy()
    if is_offpeak(now):
        return int(pol.get("per_key_cap") or 7)
    return int(pol.get("onpeak_per_key_cap") or 3)


def seconds_until_next_offpeak(now: Optional[datetime] = None) -> int:
    """Seconds until the next window start (e.g. the next 22:00 Asia/Shanghai)."""
    win = offpeak_window()
    now = _as_tz(now or _now_in_tz(win["tz"]), win["tz"])
    delta_min = (win["start_min"] - _minutes_of_day(now)) % MINUTES_PER_DAY
    if delta_min == 0:
        delta_min = MINUTES_PER_DAY
    return max(1, delta_min * 60 - now.second)


def effective_model(requested: str = "", now: Optional[datetime] = None) -> str:
    """Preserve an explicit model; ordinary unspecified work defaults to Flash.

    ``now`` remains a compatibility argument. Discounts change price/capacity,
    never the caller's selected model or authority to escalate it.
    """
    return (requested or "").strip() or "qwen3.8-flash"


def _load_config() -> Dict[str, Any]:
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def list_keys() -> List[Dict[str, str]]:
    """Return [{name, api_key}] without printing. Prefer token-plan.api_keys."""
    cfg = _load_config()
    tp = cfg.get("token-plan") or {}
    out: List[Dict[str, str]] = []
    seen = set()
    for entry in tp.get("api_keys") or []:
        name = (entry.get("name") or "").strip()
        val = (entry.get("api_key") or "").strip()
        if not name or not val or name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "api_key": val})
    if not out:
        legacy = tp.get("api_key") or ""
        if legacy:
            out.append({"name": "legacy", "api_key": legacy})
    return out


def key_names() -> List[str]:
    return [k["name"] for k in list_keys()]


def _key_value(name: str) -> str:
    for k in list_keys():
        if k["name"] == name:
            return k["api_key"]
    _die(f"unknown key name {name!r}", 2)
    return ""


def _ensure_slots() -> None:
    """Original-owner write preflight; never invoked by read-only admission.

    Legacy installations created this directory under the caller's umask.
    Safely tighten only an owned, stable physical final directory; changing
    existing cooldown file bytes or clearing a provider restriction is forbidden.
    """
    os.makedirs(SLOTS_ROOT, mode=0o700, exist_ok=True)
    required = ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC")
    if not all(hasattr(os, flag) for flag in required):
        raise RuntimeError("BAILIAN_SLOTS_ROOT_CUSTODY_UNAVAILABLE")
    try:
        fd = os.open(
            SLOTS_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        )
    except OSError as exc:
        raise RuntimeError("BAILIAN_SLOTS_ROOT_UNSAFE_OR_UNREADABLE") from exc
    try:
        def qualified_current():
            opened = os.fstat(fd)
            try:
                current = os.stat(SLOTS_ROOT, follow_symlinks=False)
            except OSError as exc:
                raise RuntimeError("BAILIAN_SLOTS_ROOT_CHANGED_DURING_PREFLIGHT") from exc
            if (not stat.S_ISDIR(opened.st_mode)
                    or not stat.S_ISDIR(current.st_mode)
                    or opened.st_uid != os.geteuid()
                    or (opened.st_dev, opened.st_ino, opened.st_uid, opened.st_mode)
                       != (current.st_dev, current.st_ino, current.st_uid, current.st_mode)):
                raise RuntimeError("BAILIAN_SLOTS_ROOT_OWNERSHIP_OR_IDENTITY_REFUSED")
            return opened

        original = qualified_current()
        if original.st_mode & 0o022:
            # This is an explicit write-path migration, never a broker read.
            # Preserve existing world/group read or traverse bits while
            # removing only the unsafe group/world WRITE bits.
            requested = stat.S_IMODE(original.st_mode) & ~0o022
            try:
                os.fchmod(fd, requested)
            except OSError as exc:
                raise RuntimeError("BAILIAN_SLOTS_ROOT_MODE_REPAIR_REFUSED") from exc
            final = qualified_current()
            if final.st_mode & 0o022:
                raise RuntimeError("BAILIAN_SLOTS_ROOT_MODE_REPAIR_UNVERIFIED")
            print("BAILIAN_SLOTS_ROOT_LEGACY_MODE_TIGHTENED", file=sys.stderr)
    finally:
        os.close(fd)


def _with_lock() -> IO[str]:
    _ensure_slots()
    fh = open(LOCK_PATH, "a+")
    fcntl.flock(fh, fcntl.LOCK_EX)
    return fh


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _name_dir(name: str) -> str:
    return os.path.join(SLOTS_ROOT, name)


def _cooldown_path(name: str) -> str:
    return os.path.join(SLOTS_ROOT, f"{name}.cooldown")


def _count_path(name: str) -> str:
    return os.path.join(SLOTS_ROOT, f"{name}.429count")


def prune_stale(name: str) -> int:
    """Remove slot files whose pid is gone OR whose mtime is older than 6 h.
    Returns remaining active count."""
    d = _name_dir(name)
    if not os.path.isdir(d):
        return 0
    now = int(time.time())
    stale_mtime = now - 6 * 3600
    alive = 0
    for fn in os.listdir(d):
        path = os.path.join(d, fn)
        if not os.path.isfile(path):
            continue
        # PID-based check
        try:
            pid = int(fn)
        except ValueError:
            # Non-numeric filename: not a PID marker, leave it alone.
            # (Only PID markers are written by pick/release.)
            continue
        if _pid_alive(pid):
            alive += 1
            continue
        # Dead PID — remove.
        try:
            os.unlink(path)
        except OSError:
            pass
        continue
    # Second pass: remove markers whose mtime is stale even if PID is alive
    # (e.g. pid-reuse edge case where a new process got the same PID).
    for fn in os.listdir(d):
        path = os.path.join(d, fn)
        if not os.path.isfile(path):
            continue
        try:
            pid = int(fn)
        except ValueError:
            continue
        try:
            mtime = int(os.path.getmtime(path))
        except OSError:
            continue
        if mtime < stale_mtime:
            try:
                os.unlink(path)
            except OSError:
                pass
    return alive


def cooldown_rank_readonly(name: str) -> int:
    """Read-only, directory-bound local cooldown classification.

    0 verified absent/expired; 1 unknown; 2 live 429 soft throttle;
    3 live non-429 hard denial. Never delete, write or pick a key.
    """
    if (not isinstance(name, str) or not name or len(name) > 128
            or "/" in name or "\x00" in name or name in (".", "..")):
        return 1
    # A directory fd binds file reads to the original owned slots directory;
    # O_NOFOLLOW rejects a symlinked *final* directory component. Installed
    # generation ext/slots may itself be a trusted intermediate state link.
    if not all(hasattr(os, x) for x in ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC")):
        return 1
    try:
        root_fd = os.open(
            SLOTS_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        )
    except OSError:
        return 1
    try:
        directory = os.fstat(root_fd)
        if (not stat.S_ISDIR(directory.st_mode)
                or directory.st_uid != os.geteuid()
                or directory.st_mode & 0o022):
            return 1

        def bound_directory() -> bool:
            try:
                current = os.stat(SLOTS_ROOT, follow_symlinks=False)
            except OSError:
                return False
            return (
                stat.S_ISDIR(current.st_mode)
                and (directory.st_dev, directory.st_ino, directory.st_uid,
                     directory.st_mode) ==
                    (current.st_dev, current.st_ino, current.st_uid,
                     current.st_mode)
            )

        entry = name + ".cooldown"
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | os.O_NOFOLLOW
        try:
            fd = os.open(entry, flags, dir_fd=root_fd)
        except FileNotFoundError:
            return 0 if bound_directory() else 1
        except OSError:
            return 1
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode)
                    or before.st_uid != os.geteuid()
                    or before.st_mode & 0o022
                    or before.st_size < 1 or before.st_size > 256):
                return 1
            data = os.read(fd, 257)
            after = os.fstat(fd)
            observed = os.stat(entry, dir_fd=root_fd, follow_symlinks=False)
            identity = lambda st: (
                st.st_dev, st.st_ino, st.st_size, st.st_mode, st.st_uid,
                st.st_mtime_ns, st.st_ctime_ns,
            )
            if (len(data) != before.st_size or identity(before) != identity(after)
                    or identity(before) != identity(observed)
                    or not bound_directory()):
                return 1
            parts = data.decode("utf-8").strip().split(None, 1)
            if len(parts) != 2 or not parts[1].strip():
                return 1
            value = float(parts[0])
            if not math.isfinite(value):
                return 1
            expiry = int(value)
            if expiry <= int(time.time()):
                return 0
            return 2 if parts[1] == "http_429" else 3
        except (OSError, ValueError, UnicodeError, OverflowError, IndexError):
            return 1
        finally:
            os.close(fd)
    finally:
        os.close(root_fd)


def cooldown_info(name: str) -> Optional[Tuple[int, str]]:
    """Return (expiry_epoch, reason) if an unexpired cooldown exists."""
    path = _cooldown_path(name)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            line = fh.readline().strip()
    except OSError:
        return None
    if not line:
        return None
    parts = line.split(None, 1)
    try:
        expiry = int(float(parts[0]))
    except (ValueError, IndexError):
        return None
    reason = parts[1] if len(parts) > 1 else ""
    now = int(time.time())
    if expiry <= now:
        try:
            os.unlink(path)
        except OSError:
            pass
        return None
    return expiry, reason


def _read_429count(name: str) -> List[int]:
    """Return sorted list of epoch timestamps of recent 429s on this key."""
    path = _count_path(name)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            content = fh.read().strip()
    except OSError:
        return []
    if not content:
        return []
    try:
        epochs = [int(float(x)) for x in content.split()]
    except ValueError:
        return []
    return sorted(epochs)


def _write_429count(name: str, epochs: List[int]) -> None:
    """Persist the sorted epoch list for 429 timestamps."""
    path = _count_path(name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(str(int(e)) for e in sorted(epochs)) + "\n")
    os.replace(tmp, path)


def _adaptive_429_seconds(name: str) -> int:
    """Compute adaptive 429 cooldown in seconds for this key.
    First 429 → 120 s; each further one within 60 min doubles (240, 480, 960);
    cap 1800 s. Counter resets when 60 min pass with no 429.
    """
    now = int(time.time())
    cutoff = now - 3600
    epochs = [e for e in _read_429count(name) if e > cutoff]
    count = len(epochs) + 1  # +1 for the one being recorded now
    if count == 1:
        base = 120
    else:
        base = 120 * (2 ** (count - 1))
    return min(base, 1800)


def active_count(name: str) -> int:
    return prune_stale(name)


def usable_names() -> List[str]:
    """Configured keys. Keys in non-429 cooldown are excluded; 429 keys are included
    (they can still handle reduced traffic at their soft cap)."""
    names = []
    for name in key_names():
        cd = cooldown_info(name)
        if cd is None:
            names.append(name)
        else:
            reason = cd[1] if len(cd) > 1 else ""
            if reason == "http_429":
                names.append(name)
    return names


def _effective_cap_for_key(name: str) -> int:
    """Effective per-key cap: 0 for non-429 cooldown; soft cap for 429 cooldown."""
    rank = cooldown_rank_readonly(name)
    cap = current_per_key_cap()
    if rank in (1, 3):
        # Unsafe/unreadable evidence is NOT permission to re-admit a possibly
        # 401/403/402-denied credential. Keep provider access fail-closed.
        return 0
    if rank == 0:
        # Proven absent or expired: ordinary policy cap.
        return cap
    # A verified live 429 retains the existing reduced soft-cap policy.
    pol = load_policy()
    if not pol.get("soft_cap_on_429", False):
        return cap
    soft = _read_soft_cap(name)
    if soft is None:
        return cap
    return max(3, min(cap, soft - 1))


def total_cap() -> int:
    """Sum of effective per-key caps across all keys.

    Keys in 429-cooldown contribute their soft cap (never less than 3).
    Every usable key contributes at least 3 even during cooldown.
    """
    cap = 0
    for name in key_names():
        cap += _effective_cap_for_key(name)
    return cap


def next_usable_in() -> int:
    """Seconds until the earliest cooldown frees a key; 0 if one is pickable now.

    Mirrors `pick`'s admission rules (not in non-429 cooldown, active slots
    under the effective per-key cap). Keys in 429-cooldown are treated as
    available at their soft cap, so next_usable_in returns 0 if any such key
    has headroom. Returns -1 when waiting cannot help: no keys configured, or
    every key is at its effective cap with no cooldown left to expire.
    Never returns a key name or value.
    """
    names = key_names()
    if not names:
        return -1
    base_cap = current_per_key_cap()
    now = int(time.time())
    soonest: Optional[int] = None
    for name in names:
        cd = cooldown_info(name)
        if cd is None:
            eff_cap = base_cap
        else:
            reason = cd[1] if len(cd) > 1 else ""
            if reason != "http_429":
                # Non-429 cooldown: wait for it to clear.
                remain = max(1, cd[0] - now)
                if soonest is None or remain < soonest:
                    soonest = remain
                continue
            eff_cap = _effective_cap_for_key(name)
        if prune_stale(name) < eff_cap:
            return 0
    return soonest if soonest is not None else -1


def pick(
    pid: Optional[int] = None,
    skip: Optional[List[str]] = None,
    prefer: Optional[str] = None,
    require: Optional[str] = None,
) -> str:
    """Least-loaded key under its effective per-key cap. Records <pid>.

    `prefer` is a soft preference for unleased callers. `require` restricts
    selection to the exact outer-lease account; an unavailable account fails
    before any other account slot is touched. Never prints a key value.
    """
    pid = int(pid if pid is not None else os.getppid())
    if require is not None and not re.fullmatch(r"[A-Za-z0-9._-]+", require):
        _die("required Bailian account is invalid", 2)
    skip_set = set(skip or [])
    extra = os.environ.get("BAILIAN_PICK_SKIP") or ""
    if extra.strip():
        skip_set.update(x.strip() for x in extra.split(",") if x.strip())
    prefer = (prefer or os.environ.get("BAILIAN_PREFER") or os.environ.get("POOL_ACCOUNT") or "").strip()
    if prefer in skip_set:
        prefer = ""
    base_cap = current_per_key_cap()
    lock = _with_lock()
    try:
        candidates: List[Tuple[int, str]] = []
        names = key_names()
        if require is not None:
            if require not in names:
                _die(f"REQUIRED_ACCOUNT_UNAVAILABLE account={require} reason=not_configured", 3)
            if require in skip_set:
                _die(f"REQUIRED_ACCOUNT_UNAVAILABLE account={require} reason=excluded", 3)
            names = [require]
        unavailable_reason = "at_capacity"
        for name in names:
            if name in skip_set:
                continue
            cd = cooldown_info(name)
            if cd is None:
                # No cooldown: use base per-key cap.
                eff_cap = base_cap
                reason = ""
            else:
                reason = cd[1] if len(cd) > 1 else ""
                if reason != "http_429":
                    # Non-429 cooldown: key is not available.
                    unavailable_reason = "cooldown"
                    continue
                # 429-cooldown key: use soft cap, key stays in the pool.
                eff_cap = _effective_cap_for_key(name)
            n = prune_stale(name)
            if n >= eff_cap:
                continue
            candidates.append((n, name))
        if not candidates:
            if require is not None:
                _die(f"REQUIRED_ACCOUNT_UNAVAILABLE account={require} reason={unavailable_reason}", 3)
            _die("no usable Bailian key (all cooling or at cap)", 3)
        preferred = [c for c in candidates if prefer and c[1] == prefer]
        if preferred:
            name = preferred[0][1]
        else:
            candidates.sort(key=lambda t: (t[0], t[1]))
            name = candidates[0][1]
        d = _name_dir(name)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, str(pid))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"{pid} {int(time.time())}\n")
        return name
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def release(name: str, pid: int) -> None:
    path = os.path.join(_name_dir(name), str(int(pid)))
    try:
        os.unlink(path)
    except OSError:
        pass


def cooldown(name: str, seconds: int, reason: str) -> int:
    """Write ext/slots/bailian/<name>.cooldown. Returns expiry epoch.

    For reason='http_429', uses adaptive cooldown and records the 429 event.
    """
    if name not in key_names():
        _die(f"unknown key name {name!r}", 2)
    reason = " ".join(str(reason).split()) or "unspecified"
    now_epoch = int(time.time())

    lock = _with_lock()
    try:
        if reason == "http_429":
            # Compute adaptive duration BEFORE writing the new epoch so the count
            # reflects only prior events (not this one yet).
            # Prune old entries first so they don't inflate the count.
            cutoff = now_epoch - 3600
            epochs = [e for e in _read_429count(name) if e > cutoff]
            count = len(epochs) + 1   # +1 for the event being recorded now
            if count == 1:
                seconds = 120
            else:
                seconds = min(120 * (2 ** (count - 1)), 1800)
            # Record active count at moment of 429 for soft-cap calculation.
            active = active_count(name)
            # Now persist the new epoch to the count file.
            epochs.append(now_epoch)
            _write_429count(name, epochs)
            _write_soft_cap(name, active)
        else:
            # Non-429 cooldown: clear any recorded 429 history.
            _write_429count(name, [])
            _clear_soft_cap(name)

        seconds = max(1, int(seconds))
        expiry = now_epoch + seconds
        path = _cooldown_path(name)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(f"{expiry} {reason}\n")
        os.replace(tmp, path)
        return expiry
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def _soft_cap_path(name: str) -> str:
    return os.path.join(SLOTS_ROOT, f"{name}.softcap")


def _read_soft_cap(name: str) -> Optional[int]:
    """Active count at time of 429, used to compute soft cap."""
    path = _soft_cap_path(name)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return None


def _write_soft_cap(name: str, active: int) -> None:
    path = _soft_cap_path(name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(f"{active}\n")
    os.replace(tmp, path)


def _clear_soft_cap(name: str) -> None:
    path = _soft_cap_path(name)
    try:
        os.unlink(path)
    except OSError:
        pass


def _codex_key_value(name: str) -> str:
    """Load one exact account privately; neither selection nor a new lease.

    The wrapper owns the key slot and broker lease. Recheck the bound account
    before both preflight and exec so a missing/replaced config cannot start a
    task with an inherited or empty credential. Never format a config/exec
    exception: malformed private input must not reach stderr through its repr.
    """
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        _die("BAILIAN_CODEX_ACCOUNT_INVALID", 78)
    if os.environ.get("LANE_LEASED") == "1" and name != os.environ.get("POOL_ACCOUNT"):
        _die("BAILIAN_CODEX_OUTER_ACCOUNT_MISMATCH", 78)
    try:
        value = _key_value(name)
    except (OSError, ValueError, TypeError, AttributeError, KeyError, SystemExit):
        _die("BAILIAN_CODEX_KEY_UNAVAILABLE", 75)
    if not isinstance(value, str) or not value or "\x00" in value:
        _die("BAILIAN_CODEX_KEY_UNAVAILABLE", 75)
    return value


def status_lines() -> List[str]:
    pol = load_policy()
    cap = current_per_key_cap()
    off = is_offpeak()
    win = offpeak_window(pol)
    models = discounted_models(pol)
    default_model = effective_model()
    soft_on = pol.get("soft_cap_on_429", False)
    lines = [
        f"offpeak={'yes' if off else 'no'} window={win['start']}-{win['end']} {win['tz']} "
        f"discounted={','.join(models) if models else 'none'} "
        f"default_model={default_model or 'none'}",
        f"cap_per_key={cap} per_key_cap={int(pol.get('per_key_cap') or 7)} "
        f"onpeak_per_key_cap={int(pol.get('onpeak_per_key_cap') or 3)} "
        f"soft_cap_on_429={'yes' if soft_on else 'no'} "
        "verify=alibaba_published_schedule",
    ]
    usable = 0
    for name in key_names():
        active = active_count(name)
        eff_cap = _effective_cap_for_key(name)
        cd = cooldown_info(name)
        epochs = _read_429count(name)
        now = int(time.time())
        recent = [e for e in epochs if e > now - 3600]
        cnt429 = len(recent)
        if cd is None:
            cd_s = "cooldown=no"
            usable += 1
        else:
            expiry, reason = cd
            remain = max(0, expiry - now)
            cd_s = f"cooldown=yes remain={remain}s expiry={expiry} reason={reason}"
        lines.append(
            f"name={name} active={active} cap={cap} eff_cap={eff_cap} "
            f"cnt429_60min={cnt429} {cd_s}"
        )
    lines.append(f"usable={usable} total_cap={total_cap()}")
    return lines


def _item_text(item: Dict[str, Any]) -> str:
    if not isinstance(item, dict):
        return ""
    kind = item.get("type") or ""
    if kind == "agent_message":
        return (item.get("text") or "").rstrip() + ("\n" if item.get("text") else "")
    if kind == "error":
        msg = item.get("message") or item.get("text") or ""
        return f"[error] {msg}\n" if msg else ""
    if kind == "command_execution":
        cmd = item.get("command") or ""
        out = item.get("aggregated_output") or ""
        rc = item.get("exit_code")
        bits = [f"$ {cmd}".rstrip()]
        if out:
            bits.append(out.rstrip())
        if rc is not None:
            bits.append(f"(exit {rc})")
        return "\n".join(bits) + "\n"
    if kind == "reasoning":
        return ""
    text = item.get("text") or item.get("message") or ""
    return (text.rstrip() + "\n") if text else ""


def stream_jsonl(in_f: IO[str], out_f: IO[str], thread_path: str, raw_path: Optional[str] = None) -> Optional[str]:
    """Filter Codex --json JSONL to plain text. Persist thread/session id."""
    thread_id = None
    raw_fh = open(raw_path, "w", encoding="utf-8") if raw_path else None
    try:
        for line in in_f:
            if raw_fh is not None:
                raw_fh.write(line)
                raw_fh.flush()
            s = line.strip()
            if not s:
                continue
            try:
                ev = json.loads(s)
            except json.JSONDecodeError:
                out_f.write(line)
                out_f.flush()
                continue
            if not isinstance(ev, dict):
                continue
            et = ev.get("type") or ""
            tid = ev.get("thread_id") or ev.get("session_id")
            if isinstance(tid, str) and tid:
                thread_id = tid
                if thread_path:
                    tmp = thread_path + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as tf:
                        tf.write(tid + "\n")
                    os.replace(tmp, thread_path)
            if et == "thread.started":
                continue
            if et in ("error", "turn.failed"):
                err = ev.get("error") if isinstance(ev.get("error"), dict) else {}
                msg = ev.get("message") or (err or {}).get("message") or ev.get("error") or ""
                if isinstance(msg, dict):
                    msg = msg.get("message") or json.dumps(msg)
                if msg:
                    out_f.write(str(msg).rstrip() + "\n")
                    out_f.flush()
                continue
            if et == "item.completed":
                text = _item_text(ev.get("item") or {})
                if text:
                    out_f.write(text)
                    if not text.endswith("\n"):
                        out_f.write("\n")
                    out_f.flush()
                continue
            payload = ev.get("payload")
            if isinstance(payload, dict):
                sid = payload.get("session_id") or payload.get("id")
                if isinstance(sid, str) and sid and et == "session_meta":
                    thread_id = sid
                    if thread_path:
                        tmp = thread_path + ".tmp"
                        with open(tmp, "w", encoding="utf-8") as tf:
                            tf.write(sid + "\n")
                        os.replace(tmp, thread_path)
                ptype = payload.get("type")
                if ptype == "agent_message":
                    msg = payload.get("message") or payload.get("text") or ""
                    if msg:
                        out_f.write(str(msg).rstrip() + "\n")
                        out_f.flush()
    finally:
        if raw_fh is not None:
            raw_fh.close()
    return thread_id


def cmd_pick(argv: List[str]) -> int:
    prefer = None
    require = None
    rest: List[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--require":
            if i + 1 >= len(argv) or require is not None:
                _die("usage: pick [--prefer NAME | --require NAME]", 2)
            require = argv[i + 1]
            i += 2
            continue
        if argv[i] == "--prefer" and i + 1 < len(argv):
            prefer = argv[i + 1]
            i += 2
            continue
        rest.append(argv[i])
        i += 1
    if rest and prefer is None:
        prefer = rest[0]
    if require is not None and (prefer is not None or rest):
        _die("usage: pick [--prefer NAME | --require NAME]", 2)
    name = pick(prefer=prefer, require=require)
    print(name)
    return 0


def cmd_env(argv: List[str]) -> int:
    # Keep an explicit fail-closed response for a mismatched old wrapper. This
    # command must never read private config or reconstruct the old export.
    _die("BAILIAN_ENV_EXPORT_RETIRED: use exec-codex", 78)
    return 78


def cmd_check_key(argv: List[str]) -> int:
    """Private readiness check for the wrapper's existing key-wait loop."""
    if len(argv) != 1:
        _die("usage: check-key <name>", 2)
    _codex_key_value(argv[0])
    return 0


def cmd_exec_codex(argv: List[str]) -> int:
    """Replace this process with Codex exec; no key in shell/argv/output.

    Only the fixed `codex exec` entry point is supported. PATH, all caller exec
    arguments, inherited I/O, process identity and the eventual Codex status
    retain the incumbent wrapper contract. This helper never forks/retries a
    worker or acquires/releases the wrapper's slots and leases.
    """
    if len(argv) < 2 or argv[1] != "--":
        _die("usage: exec-codex <name> -- <codex exec arguments...>", 2)
    value = _codex_key_value(argv[0])
    child_env = os.environ.copy()
    child_env["BAILIAN_API_KEY"] = value
    try:
        os.execvpe("codex", ["codex", "exec", *argv[2:]], child_env)
    except FileNotFoundError:
        _die("BAILIAN_CODEX_EXEC_UNAVAILABLE", 127)
    except OSError:
        _die("BAILIAN_CODEX_EXEC_REFUSED", 126)
    except (ValueError, TypeError):
        _die("BAILIAN_CODEX_EXEC_ENV_INVALID", 78)
    _die("BAILIAN_CODEX_EXEC_NOT_REPLACED", 126)
    return 126


def cmd_release(argv: List[str]) -> int:
    if len(argv) < 2:
        _die("usage: release <name> <pid>", 2)
    release(argv[0], int(argv[1]))
    return 0


def cmd_cooldown(argv: List[str]) -> int:
    if len(argv) < 3:
        _die("usage: cooldown <name> <seconds> <reason>", 2)
    name, seconds, reason = argv[0], argv[1], " ".join(argv[2:])
    expiry = cooldown(name, int(seconds), reason)
    print(f"cooldown name={name} seconds={int(seconds)} expiry={expiry} reason={reason}")
    return 0


def cmd_preflight_slots(argv: List[str]) -> int:
    """Explicit original-owner release preflight; no provider or key access."""
    if argv:
        _die("usage: preflight-slots", 2)
    _ensure_slots()
    print("BAILIAN_SLOTS_ROOT_VERIFIED")
    return 0


def cmd_status(argv: List[str]) -> int:
    for line in status_lines():
        print(line)
    return 0


def cmd_total_cap(argv: List[str]) -> int:
    print(total_cap())
    return 0


def cmd_next_usable_in(argv: List[str]) -> int:
    print(next_usable_in())
    return 0


def cmd_model(argv: List[str]) -> int:
    print(effective_model(argv[0] if argv else ""))
    return 0


def cmd_stream(argv: List[str]) -> int:
    """Internal: filter Codex JSONL on stdin. argv: <thread-file> [raw-file]."""
    if not argv:
        _die("usage: stream <thread-file> [raw-file]", 2)
    thread_path = argv[0]
    raw_path = argv[1] if len(argv) > 1 else None
    stream_jsonl(sys.stdin, sys.stdout, thread_path, raw_path)
    return 0


def cmd_seconds_until_offpeak(argv: List[str]) -> int:
    print(seconds_until_next_offpeak())
    return 0


COMMANDS = {
    "pick": cmd_pick,
    "env": cmd_env,
    "check-key": cmd_check_key,
    "exec-codex": cmd_exec_codex,
    "release": cmd_release,
    "cooldown": cmd_cooldown,
    "status": cmd_status,
    "preflight-slots": cmd_preflight_slots,
    "total_cap": cmd_total_cap,
    "next_usable_in": cmd_next_usable_in,
    "model": cmd_model,
    "stream": cmd_stream,
    "seconds_until_offpeak": cmd_seconds_until_offpeak,
}


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 2
    cmd = argv[0]
    if cmd not in COMMANDS:
        _die(f"unknown command {cmd!r}\n" + (__doc__ or ""), 2)
    try:
        return COMMANDS[cmd](argv[1:])
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
