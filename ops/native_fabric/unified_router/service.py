"""launchd entrypoint for the unified fabric router (loopback only).

All routing, admission and selection remain owned by gateway.py; this module
only loads the operator env file and runs Uvicorn.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import stat

_ALLOWED = frozenset({
    "FABRIC_MAX_ATTEMPTS",
    "FABRIC_ROUTER_TOKEN", "FABRIC_ROUTES_JSON", "FABRIC_GATEWAY_STATE_DIR",
    "FABRIC_AUTH_STORE", "FABRIC_MAX_BODY_BYTES", "FABRIC_UPSTREAM_TIMEOUT_S",
    "FABRIC_ROUTE_COOLDOWN_S",
    "FABRIC_MAX_IN_FLIGHT", "FABRIC_REQUEST_TIMEOUT_S", "FABRIC_REQUEST_BODY_TIMEOUT_S",
    "FABRIC_MAX_RESPONSE_BYTES", "FABRIC_MAX_SSE_EVENT_BYTES",
    # Loopback gateway tokens for the incumbent fabric edges this router composes.
    "FABRIC_ANTHROPIC_GATEWAY_TOKEN", "FABRIC_EXPERIENTIAL_GATEWAY_TOKEN",
})


def load_environment(path: Path) -> dict[str, str]:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1
                or not 0 < before.st_size <= 32768):
            raise ValueError("router environment metadata is unsafe")
        raw = os.read(fd, 32769)
        after = os.fstat(fd)
        if (len(raw) != before.st_size or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ctime_ns != after.st_ctime_ns):
            raise ValueError("router environment changed during read")
    finally:
        os.close(fd)
    result = {}
    for line in raw.decode("utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if not separator or name not in _ALLOWED or name in result or "\x00" in value:
            raise ValueError("router environment has an invalid field")
        result[name] = value
    if not result.get("FABRIC_ROUTER_TOKEN") or not result.get("FABRIC_ROUTES_JSON"):
        raise ValueError("router credentials are unavailable")
    routes = Path(result["FABRIC_ROUTES_JSON"]).expanduser()
    if not routes.is_absolute():
        raise ValueError("FABRIC_ROUTES_JSON must be absolute")
    document = json.loads(routes.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("routes"), list):
        raise ValueError("routes document is invalid")
    return result


def logging_config() -> dict:
    """Render terminal receipts through the existing Uvicorn/launchd sink."""
    from uvicorn.config import LOGGING_CONFIG

    config = copy.deepcopy(LOGGING_CONFIG)
    config["loggers"]["ops.native_fabric.unified_router.gateway"] = {
        "handlers": ["default"], "level": "INFO", "propagate": False,
    }
    return config


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8313)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535 or not args.env_file.is_absolute():
        raise ValueError("router service target is invalid")
    values = load_environment(args.env_file)
    for name in _ALLOWED:
        os.environ.pop(name, None)
    os.environ.update(values)
    import socket as _socket
    import uvicorn

    # Zero-downtime reload: bind the listener with SO_REUSEPORT so a
    # replacement process can bind the same port while this one drains
    # in-flight streams. On SIGTERM uvicorn closes this listener and
    # finishes active responses (bounded by timeout_graceful_shutdown)
    # before exiting. launchd must also allow the old process enough
    # ExitTimeOut to finish its drain.
    sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEPORT, 1)
    sock.setsockopt(_socket.IPPROTO_TCP, _socket.TCP_NODELAY, 1)
    sock.bind(("127.0.0.1", args.port))
    sock.listen(2048)
    config = uvicorn.Config(
        "ops.native_fabric.unified_router.gateway:create_app", factory=True,
        host="127.0.0.1", port=args.port, workers=1, access_log=False,
        log_config=logging_config(),
        timeout_graceful_shutdown=25,
    )
    uvicorn.Server(config).run(sockets=[sock])


if __name__ == "__main__":
    main()
