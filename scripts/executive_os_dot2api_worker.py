#!/usr/bin/env python3
"""Entrypoint for the existing Executive WorkerBroker with a Dot2API adapter."""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from ops.executive_os.dot2api_worker_service import main


if __name__ == "__main__":
    raise SystemExit(main(release_root=_ROOT))
