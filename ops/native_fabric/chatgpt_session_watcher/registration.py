"""Load the fabric worker-kind manifest. One file, read by Python and the MCP facade."""

from __future__ import annotations

import json
from pathlib import Path

_PATH = Path(__file__).with_name("registration.json")
MANIFEST = json.loads(_PATH.read_text(encoding="utf-8"))

KIND = MANIFEST["kind"]
TASK_CLASS = MANIFEST["task_class"]
POOL = MANIFEST["pool"]
MODEL = MANIFEST["model"]
HOST = MANIFEST["host"]
DEFAULT_MODE = MANIFEST["default_mode"]
LIVE_ENV = "MMX_WATCHER_ALLOW_LIVE"
