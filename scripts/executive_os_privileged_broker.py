#!/usr/bin/env python3
"""Root launchd entrypoint for the Mastermind privileged-action broker."""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Sequence

_RELEASE_ROOT = Path(__file__).resolve().parents[1]
if str(_RELEASE_ROOT) not in sys.path:
    sys.path.insert(0, str(_RELEASE_ROOT))

from control_plane.executive_privileged_broker import PrivilegedBrokerConfig, run_broker


CONFIG_PATH = Path("/Library/Application Support/MastermindExecutive/config/privileged-broker.json")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the Mastermind privileged action socket")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--config", type=Path, required=True)
    return parser


def load_config(path: Path) -> PrivilegedBrokerConfig:
    if path != CONFIG_PATH:
        raise RuntimeError("privileged broker requires the fixed installed config path")
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise RuntimeError("privileged broker config is not a regular file")
    if info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o400:
        raise RuntimeError("privileged broker config ownership/mode drifted")
    if info.st_size <= 0 or info.st_size > 64 * 1024:
        raise RuntimeError("privileged broker config size is invalid")
    value = json.loads(path.read_text(encoding="utf-8"))
    return PrivilegedBrokerConfig.from_mapping(value)


def main(argv: Sequence[str] | None = None) -> int:
    # Let argparse reject malformed invocation before any host trust check so
    # isolated wrapper probes fail cleanly without a traceback.
    args = _parser().parse_args(argv)
    if os.geteuid() != 0:
        raise RuntimeError("privileged broker entrypoint must run as root")
    if args.command != "serve":  # pragma: no cover - argparse owns this invariant
        raise RuntimeError("unsupported privileged broker command")
    config = load_config(args.config)
    run_broker(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
