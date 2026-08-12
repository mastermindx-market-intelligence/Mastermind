"""Run the Phase 1C-A distinct-principal secret canary without reading secrets."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from control_plane.executive_canary import (
    SecretCanaryConfig,
    SecretCanaryError,
    run_secret_canary,
)


def _absolute_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("path must be absolute")
    return path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Issue a hash/status-only Executive secret-canary receipt."
    )
    parser.add_argument("--expected-worker-uid", type=int, required=True)
    parser.add_argument("--expected-worker-gid", type=int, required=True)
    parser.add_argument("--control-uid", type=int, required=True)
    parser.add_argument("--control-gid", type=int, required=True)
    parser.add_argument("--control-env-sentinel", required=True)
    parser.add_argument("--control-environment-probe-sha256", required=True)
    parser.add_argument(
        "--administrative-checkout-sentinel",
        type=_absolute_path,
        required=True,
    )
    parser.add_argument("--executive-database", type=_absolute_path, required=True)
    parser.add_argument(
        "--other-worker-home-sentinel",
        type=_absolute_path,
        required=True,
    )
    parser.add_argument(
        "--forbidden-production-sentinel",
        type=_absolute_path,
        required=True,
    )
    parser.add_argument("--codex-home", type=_absolute_path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    config = SecretCanaryConfig(
        expected_worker_uid=arguments.expected_worker_uid,
        expected_worker_gid=arguments.expected_worker_gid,
        control_uid=arguments.control_uid,
        control_gid=arguments.control_gid,
        control_environment_sentinel=arguments.control_env_sentinel,
        control_environment_probe_sha256=arguments.control_environment_probe_sha256,
        administrative_checkout_sentinel=arguments.administrative_checkout_sentinel,
        executive_database=arguments.executive_database,
        other_worker_home_sentinel=arguments.other_worker_home_sentinel,
        forbidden_production_sentinel=arguments.forbidden_production_sentinel,
        codex_home=arguments.codex_home,
    )
    try:
        verdict = run_secret_canary(config)
    except SecretCanaryError as exc:
        print(f"secret canary failed: {exc.code}", file=sys.stderr)
        return 1
    json.dump(
        verdict,
        sys.stdout,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main
    raise SystemExit(main())
