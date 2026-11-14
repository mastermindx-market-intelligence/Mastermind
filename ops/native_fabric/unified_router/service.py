"""launchd entrypoint for the unified fabric router (loopback only).

All routing, admission and selection remain owned by gateway.py; this module
only loads the operator env file and runs Uvicorn.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat

_ALLOWED = frozenset({
    "FABRIC_ROUTER_TOKEN", "FABRIC_ROUTES_JSON", "FABRIC_GATEWAY_STATE_DIR",
    "FABRIC_AUTH_STORE", "FABRIC_MAX_BODY_BYTES", "FABRIC_UPSTREAM_TIMEOUT_S",
    "FABRIC_ROUTE_COOLDOWN_S", "FABRIC_MAX_ATTEMPTS",
    # Bounded hold-for-capacity / free-route pacing knobs (router-wide).
    "FABRIC_CAPACITY_WAIT_S", "FABRIC_FREE_HOLD_S",
    # Peak-window GLM conservation knobs (router-wide).
    "FABRIC_PEAK_TZ", "FABRIC_PEAK_START", "FABRIC_PEAK_END",
    "FABRIC_PEAK_MIN_INTERVAL_S", "FABRIC_PEAK_DELAY_S", "FABRIC_PEAK_WAIT_S",
    # Loopback gateway tokens for the incumbent fabric edges this router composes.
    "FABRIC_ANTHROPIC_GATEWAY_TOKEN", "FABRIC_EXPERIENTIAL_GATEWAY_TOKEN",
    "CURSOR_GATEWAY_TOKEN",
    # Provider credentials referenced by routes.json `env_key` (2026-11-11):
    # lyber_prepaid was added to routes.json without extending this allowlist,
    # so every start rejected the env file and the router crash-looped.
    "LYBER_API_KEY",
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8313)
    parser.add_argument("--routes-file", type=Path, help="Bounded local staging override; no credential change")
    parser.add_argument("--no-observer-export", action="store_true", help="Isolated rollout proof must not replace live telemetry")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535 or not args.env_file.is_absolute():
        raise ValueError("router service target is invalid")
    values = load_environment(args.env_file)
    for name in _ALLOWED:
        os.environ.pop(name, None)
    os.environ.update(values)
    if args.routes_file:
        if not args.routes_file.is_absolute():
            raise ValueError("route override must be absolute")
        os.environ["FABRIC_ROUTES_JSON"] = str(args.routes_file)
    if args.no_observer_export:
        os.environ["FABRIC_OBSERVER_EXPORT_DISABLED"] = "1"
    else:
        os.environ.pop("FABRIC_OBSERVER_EXPORT_DISABLED", None)
    import socket as _socket
    import uvicorn

    # Zero-downtime reload support: bind the listener ourselves with
    # SO_REUSEPORT so a replacement process can bind the same port while this
    # one drains in-flight streams. On SIGTERM uvicorn closes this listener
    # and finishes active responses (bounded by timeout_graceful_shutdown)
    # before exiting. Requires the *old* process to hold a SO_REUSEPORT
    # socket as well; the first reload after this patch still blips once.
    import hashlib
    from ops.native_fabric.unified_router.capacity_fabric_observer import create_app
    app = create_app()
    release_root = Path(__file__).resolve().parents[3]
    manifest = json.loads((release_root / "SOURCE.json").read_text())
    runtime_files = manifest.get("runtime_files")
    if not isinstance(runtime_files, dict) or not runtime_files:
        raise ValueError("runtime source manifest is missing")
    actual_files = {}
    for relative, expected in runtime_files.items():
        target = release_root / relative
        if ".." in Path(relative).parts or Path(relative).is_absolute():
            raise ValueError("invalid runtime manifest path")
        actual_files[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
    # Local edits remain a supported workflow. Report measured running-source
    # identity instead of trusting a directory label or requiring a GitHub release.
    measured = hashlib.sha256(json.dumps(actual_files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    app.state.runtime_generation = "model-tier-20261111-" + measured[:16]
    app.state.source_matches_manifest = actual_files == runtime_files
    print(json.dumps({"router_started_source": app.state.runtime_generation,
                      "source_matches_manifest": app.state.source_matches_manifest,
                      "pid": os.getpid()}), flush=True)
    config = uvicorn.Config(
        app, host="127.0.0.1", port=args.port, workers=1, access_log=False,
        timeout_graceful_shutdown=960, limit_concurrency=384,
    )
    class RouterServer(uvicorn.Server):
        def handle_exit(self, sig, frame):
            app.state.model_policy.draining = True
            app.state.model_policy.changed.set()
            return super().handle_exit(sig, frame)
    server = RouterServer(config)
    sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEPORT, 1)
    sock.setsockopt(_socket.IPPROTO_TCP, _socket.TCP_NODELAY, 1)
    sock.bind(("127.0.0.1", args.port))
    sock.listen(2048)
    server.run(sockets=[sock])


if __name__ == "__main__":
    main()
