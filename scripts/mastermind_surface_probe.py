#!/usr/bin/env python3
"""Launch or describe the production-inert Mastermind HC0 surface probe."""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
from typing import Any

from integrations.mastermind_surface_probe.probe import SurfaceContextProbe
from integrations.mastermind_surface_probe.schemas import (
    ProbeConfig,
    ProbeError,
    schema_snapshot,
)
from integrations.mastermind_surface_probe.server import (
    build_mcp_server,
    build_streamable_http_app,
)

_ENV = {
    "app_realm": "MASTERMIND_SURFACE_PROBE_APP_REALM",
    "app_generation": "MASTERMIND_SURFACE_PROBE_APP_GENERATION",
    "transport_profile": "MASTERMIND_SURFACE_PROBE_TRANSPORT_PROFILE",
    "fingerprint_key_id": "MASTERMIND_SURFACE_PROBE_HMAC_KEY_ID",
    "fingerprint_key_version": "MASTERMIND_SURFACE_PROBE_HMAC_KEY_VERSION",
    "fingerprint_scope": "MASTERMIND_SURFACE_PROBE_FINGERPRINT_SCOPE",
}
_KEY_ENV = "MASTERMIND_SURFACE_PROBE_HMAC_KEY_B64"


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise ProbeError(
            "CONFIGURATION_ERROR",
            "surface probe configuration is incomplete",
        )
    return value.strip()


def load_config_from_environment() -> ProbeConfig:
    values: dict[str, Any] = {
        field: _required_env(env_name) for field, env_name in _ENV.items()
    }
    encoded = _required_env(_KEY_ENV)
    try:
        secret = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise ProbeError(
            "CONFIGURATION_ERROR",
            "surface probe configuration is invalid",
        ) from None
    values["fingerprint_secret"] = secret
    return ProbeConfig(**values)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one loopback-only, stateless, read-only Mastermind host-context "
            "MCP probe. Secure MCP Tunnel remains an outer transport."
        )
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--path", default="/mcp")
    parser.add_argument("--describe", action="store_true")
    parser.add_argument("--check-config", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.describe:
        print(json.dumps(schema_snapshot(), sort_keys=True, indent=2))
        return 0

    try:
        config = load_config_from_environment()
    except ProbeError as exc:
        raise SystemExit(exc.code) from None

    if args.check_config:
        print(
            json.dumps(
                {
                    "ok": True,
                    "app_realm": config.app_realm,
                    "app_generation": config.app_generation,
                    "transport_profile": config.transport_profile,
                    "fingerprint_key_id": config.fingerprint_key_id,
                    "fingerprint_key_version": config.fingerprint_key_version,
                    "fingerprint_scope": config.fingerprint_scope,
                },
                sort_keys=True,
            )
        )
        return 0

    if args.port < 1024 or args.port > 65535:
        raise SystemExit("CONFIGURATION_ERROR")

    probe = SurfaceContextProbe(config)
    app = build_streamable_http_app(
        build_mcp_server(probe),
        host=args.host,
        path=args.path,
    )

    import uvicorn

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="warning",
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
