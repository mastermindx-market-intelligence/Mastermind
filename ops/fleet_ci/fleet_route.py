#!/usr/bin/env python3
"""Hybrid CI router decision (used by .github/actions/fleet-route).

  fleet_route.py --mode off|hybrid|fleet-only --class std|heavy --jobs-needed N
                 [--capacity FILE] [--spill-ratio R]

Prints the `runs-on` value as JSON on stdout:
  off        -> "ubuntu-24.04"
  fleet-only -> ["self-hosted","Linux","X64","fleet","fleet-<class>"]
  hybrid     -> fleet labels when idle fleet slots of the class >= jobs_needed, or when
                idle >= 1 and idle / jobs_needed >= spill ratio (FLEET_SPILL_RATIO,
                default 1.0 = never spill a partial batch); otherwise hosted.
Missing, unreadable or not-ok capacity in hybrid mode -> hosted. An unknown mode is
treated as off. A decision line goes to stderr (no secrets are ever involved).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from typing import Any, Dict, List, Optional, Union

HOSTED = "ubuntu-24.04"
MODES = ("off", "hybrid", "fleet-only")
CLASSES = ("std", "heavy")


def fleet_labels(cls: str) -> List[str]:
    return ["self-hosted", "Linux", "X64", "fleet", f"fleet-{cls}"]


def decide(mode: str, cls: str, jobs_needed: int, capacity: Optional[Dict[str, Any]],
           spill_ratio: float = 1.0) -> Dict[str, Any]:
    mode = mode if mode in MODES else "off"
    cls = cls if cls in CLASSES else "std"
    jobs = max(1, jobs_needed)
    if mode == "off":
        return {"runner": HOSTED, "target": "hosted", "why": "mode=off"}
    if mode == "fleet-only":
        return {"runner": fleet_labels(cls), "target": "fleet", "why": "mode=fleet-only"}
    if not isinstance(capacity, dict) or capacity.get("ok") is not True:
        return {"runner": HOSTED, "target": "hosted", "why": "capacity-unavailable"}
    bucket = (capacity.get("per_class") or {}).get(cls)
    idle = bucket.get("idle") if isinstance(bucket, dict) else None
    if not isinstance(idle, int) or isinstance(idle, bool) or idle < 0:
        return {"runner": HOSTED, "target": "hosted", "why": "capacity-invalid"}
    ratio = spill_ratio if isinstance(spill_ratio, (int, float)) and math.isfinite(spill_ratio) else 1.0
    ratio = min(1.0, max(0.0, ratio))
    if idle >= jobs:
        return {"runner": fleet_labels(cls), "target": "fleet", "why": f"idle={idle}>=jobs={jobs}"}
    if idle >= 1 and ratio < 1.0 and idle / jobs >= ratio:
        return {"runner": fleet_labels(cls), "target": "fleet",
                "why": f"spill idle={idle}/jobs={jobs}>={ratio:g}"}
    return {"runner": HOSTED, "target": "hosted", "why": f"idle={idle}<jobs={jobs}"}


def runs_on_json(runner: Union[str, List[str]]) -> str:
    return json.dumps(runner, separators=(",", ":"))


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="fleet_route")
    p.add_argument("--mode", default="off")
    p.add_argument("--class", dest="cls", default="std")
    p.add_argument("--jobs-needed", default="1")
    p.add_argument("--capacity")
    p.add_argument("--spill-ratio", default="1.0")
    args = p.parse_args(argv)
    try:
        jobs = int(args.jobs_needed)
    except ValueError:
        jobs = 1
    try:
        ratio = float(args.spill_ratio)
    except ValueError:
        ratio = 1.0
    capacity = None
    if args.capacity:
        try:
            with open(args.capacity, encoding="utf-8") as fh:
                capacity = json.load(fh)
        except (OSError, ValueError):
            capacity = None
    d = decide(args.mode.strip().lower(), args.cls.strip().lower(), jobs, capacity, ratio)
    print(f"fleet-route: target={d['target']} why={d['why']}", file=sys.stderr)
    print(runs_on_json(d["runner"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
