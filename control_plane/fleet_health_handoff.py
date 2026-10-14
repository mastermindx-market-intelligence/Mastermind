"""Single latest sanitized Fleet view for the *existing* Fabric collector.

A trusted installer enrolls a private 0700 directory and narrow macOS
search/read ACL for the existing Executive service UID. The already-running
Fabric observer may call publish once per normal collector pass; this module
starts no timer, process, remote probe, watcher, event queue or authority.

The service reads only this intentionally reduced fixed file. It neither
traverses the source operator's ~/.claude hierarchy nor trusts the report
for Worker capacity/admission. No second telemetry history is retained.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import stat
import time

from common.fleet_health_contract import FLEET_WINDOWS, validate_fleet_document
from control_plane.fleet_health import read_fleet_health, unavailable_fleet

HANDOFF_FILE = "fleet-health-current.json"
HANDOFF_SCHEMA = "mastermind.fleet_health_handoff.v1"
HANDOFF_SOURCE = "fabric_host_observer"
HANDOFF_BYTES_LIMIT = 6_500_000
HANDOFF_MAX_AGE_SECONDS = 180
_WINDOW_ORDER = ("1h", "24h", "7d", "30d")


def _clock(now):
    if type(now) not in (int, float) or not math.isfinite(now) or now <= 0:
        raise ValueError("Fleet handoff invalid clock")
    return now


def _window(window):
    if type(window) is not str or window not in FLEET_WINDOWS:
        raise ValueError("Fleet handoff invalid window")
    return window


def _directory(path, *, writer):
    """Return one real protected directory FD; never resolve a symlink."""
    p = Path(path)
    if not p.is_absolute() or ".." in p.parts or "\x00" in str(p):
        raise ValueError("Fleet handoff directory unavailable")
    fd = os.open(p, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700
                or (writer and info.st_uid != os.geteuid())):
            raise ValueError("Fleet handoff directory unavailable")
        return fd, info
    except Exception:
        os.close(fd)
        raise


def _checked_bundle(document, *, window, now):
    if (type(document) is not dict or set(document) !=
            {"schema", "source", "generated_at", "windows"}
            or document["schema"] != HANDOFF_SCHEMA
            or document["source"] != HANDOFF_SOURCE):
        raise ValueError("Fleet handoff invalid schema")
    created = _clock(document["generated_at"])
    if not 0 <= now - created <= HANDOFF_MAX_AGE_SECONDS:
        raise ValueError("Fleet handoff is not current")
    windows = document["windows"]
    if type(windows) is not dict or set(windows) != set(_WINDOW_ORDER):
        raise ValueError("Fleet handoff invalid windows")
    for name in _WINDOW_ORDER:
        body = validate_fleet_document(windows[name], expected_window=name)
        if body["availability"] == "UNAVAILABLE" or body["generated_at"] != created:
            raise ValueError("Fleet handoff has no qualified source observation")
    return windows[window]


def _read_bundle(directory_fd, root_info):
    fd = os.open(HANDOFF_FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                 dir_fd=directory_fd)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != root_info.st_uid
                or info.st_nlink != 1 or info.st_size <= 0
                or info.st_size > HANDOFF_BYTES_LIMIT
                or stat.S_IMODE(info.st_mode) != 0o644):
            raise ValueError("Fleet handoff is not a qualified regular report")
        remaining = info.st_size
        chunks = []
        while remaining:
            part = os.read(fd, min(65536, remaining))
            if not part:
                raise ValueError("Fleet handoff read changed")
            chunks.append(part)
            remaining -= len(part)
        after = os.fstat(fd)
        if (info.st_size, info.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("Fleet handoff modified in place")
        return b"".join(chunks)
    finally:
        os.close(fd)


def read_fleet_health_handoff(handoff_root: Path, *, window: str, now=None):
    """Read trusted, validated 180-second advisory projection or typed UNAVAILABLE.

    This reader has no path/host selector supplied by the HTTP client. A
    separate-root read is required; private source filesystem permissions
    are never broadened or traversed by the Executive service.
    """
    window = _window(window)
    now = _clock(time.time() if now is None else now)
    descriptor = None
    try:
        descriptor, info = _directory(handoff_root, writer=False)
        raw = _read_bundle(descriptor, info)
        doc = json.loads(raw.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid numeric content")))
        return _checked_bundle(doc, window=window, now=now)
    except (OSError, ValueError, TypeError, UnicodeError):
        return unavailable_fleet(window, now)
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _unique_pairs(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("duplicate handoff key")
        data[key] = value
    return data


def publish_fleet_health_handoff(observer_root: Path, handoff_root: Path, *, now=None):
    """Called by the installed observer owner, only after its regular pass.

    The owner supplies both nonpublic roots. The output contains four
    sanitized, bounded views, atomically replacing the prior single file.
    An unqualified source aborts and retains the old file to age out; no
    fabricated current/healthy reading can be published.
    """
    now = _clock(time.time() if now is None else now)
    source_views = {}
    for window in _WINDOW_ORDER:
        doc = read_fleet_health(observer_root, window=window, now=now)
        view = validate_fleet_document(doc, expected_window=window)
        if view["availability"] == "UNAVAILABLE":
            raise ValueError("Fleet observer source unavailable")
        source_views[window] = view
    bundle = {"schema": HANDOFF_SCHEMA, "source": HANDOFF_SOURCE,
              "generated_at": now, "windows": source_views}
    _checked_bundle(bundle, window="24h", now=now)
    body = json.dumps(bundle, separators=(",", ":"), sort_keys=True,
                      ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(body) > HANDOFF_BYTES_LIMIT:
        raise ValueError("Fleet handoff response over budget")
    directory_fd = None
    temporary = "fleet-health-staging-" + secrets.token_hex(16)
    placed = False
    try:
        directory_fd, _ = _directory(handoff_root, writer=True)
        fd = os.open(temporary,
                     os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=directory_fd)
        placed = True
        with os.fdopen(fd, "wb") as output:
            output.write(body)
            output.flush()
            os.fchmod(output.fileno(), 0o644)
            os.fsync(output.fileno())
        os.replace(temporary, HANDOFF_FILE,
                   src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        placed = False
        os.fsync(directory_fd)
        return {"published": True, "schema": HANDOFF_SCHEMA,
                "sha256": hashlib.sha256(body).hexdigest(),
                "generated_at": now, "host_count": len(source_views["24h"]["hosts"]),
                "windows": list(_WINDOW_ORDER), "admission_authoritative": False}
    finally:
        if placed and directory_fd is not None:
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except OSError:
                pass
        if directory_fd is not None:
            os.close(directory_fd)


def main(argv=None):
    """One-shot existing-observer hook, not a new monitoring process.

    The source and handoff roots are trusted owner configuration, not web
    client arguments. Deliberately no timestamp override or daemon option.
    """
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="Publish one sanitized Fabric Fleet health observation")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--observer-root", type=Path, required=True)
    parser.add_argument("--handoff-root", type=Path, required=True)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    if not args.once:
        print("Fleet handoff unavailable: --once required", file=sys.stderr)
        return 2
    try:
        receipt = publish_fleet_health_handoff(args.observer_root, args.handoff_root)
    except (OSError, ValueError, TypeError):
        # Never disclose host paths or registry internals through the CLI.
        print("Fleet handoff unavailable", file=sys.stderr)
        return 75
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
