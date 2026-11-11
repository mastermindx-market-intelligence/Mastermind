"""Run the existing single-process gateway from its private host-owned env file.

This is a launchd entrypoint, not a worker scheduler. All requests, durable RPM
admissions and upstream effects remain owned by gateway.py.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat

_ALLOWED = frozenset({
    "EXPLABS_KEY_1", "EXPLABS_KEY_2", "EXPLABS_KEY_3", "EXPLABS_KEY_4",
    "FABRIC_PROXY_TOKEN", "FABRIC_GATEWAY_STATE_DIR", "EXPLABS_PLAN_POLICY",
    "EXPLABS_ACCOUNT_METADATA_ENABLED", "EXPLABS_ANTHROPIC_MODELS",
    "SAFE_RPM_PER_KEY", "SAFE_RPM_SHARED",
    "FABRIC_MAX_INFLIGHT_PER_KEY", "FABRIC_MAX_PENDING", "FABRIC_MAX_PENDING_BYTES",
    "FABRIC_MAX_QUEUE_WAIT_S", "FABRIC_MAX_BODY_BYTES",
})


def load_environment(path: Path) -> dict[str, str]:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1
                or not 0 < before.st_size <= 32768):
            raise ValueError("gateway environment metadata is unsafe")
        raw = os.read(fd, 32769)
        after = os.fstat(fd)
        if (len(raw) != before.st_size or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ctime_ns != after.st_ctime_ns):
            raise ValueError("gateway environment changed during read")
    finally:
        os.close(fd)
    result = {}
    for line in raw.decode("utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if not separator or name not in _ALLOWED or name in result or "\x00" in value:
            raise ValueError("gateway environment has an invalid field")
        result[name] = value
    if not result.get("EXPLABS_KEY_1") or not result.get("FABRIC_PROXY_TOKEN"):
        raise ValueError("gateway credentials are unavailable")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8311)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535 or not args.env_file.is_absolute():
        raise ValueError("gateway service target is invalid")
    values = load_environment(args.env_file)
    for name in _ALLOWED:
        os.environ.pop(name, None)
    os.environ.update(values)
    import uvicorn
    uvicorn.run("ops.native_fabric.experiential_proxy.gateway:app", host="127.0.0.1",
                port=args.port, workers=1, access_log=False)


if __name__ == "__main__":
    main()
