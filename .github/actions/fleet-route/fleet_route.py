#!/usr/bin/env python3
"""Hybrid CI router decision (used by .github/actions/fleet-route).

  fleet_route.py --mode off|hybrid|fleet-only --class std|heavy --jobs-needed N
                 [--capacity FILE] [--spill-ratio R]
                 [--trusted-source true|false] [--repo-private true|false]
                 [--fetch-capacity] [--github-output FILE]

Prints the `runs-on` value as JSON on stdout:
  off        -> "ubuntu-24.04"
  fleet-only -> ["self-hosted","Linux","X64","fleet","fleet-<class>"] for a TRUSTED
                source only; an untrusted source (fork PR) always routes hosted.
  hybrid     -> fleet labels when idle fleet slots of the class >= jobs_needed, or when
                idle >= 1 and idle / jobs_needed >= spill ratio (FLEET_SPILL_RATIO,
                default 1.0 = never spill a partial batch); otherwise hosted.

The trusted-source guard is binding in every mode: the caller computes it as
`github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name
== github.repository` and passes it as --trusted-source. --repo-private
(github.event.repository.private) is recorded for observability; private repositories
have no outside forks, so the guard matters while the repos are public.

--fetch-capacity (hybrid only, when --capacity is not given) runs the sibling
`fleet-capacity` script FROM THIS DIRECTORY and reads its JSON. Inside the composite
action this directory is github.action_path — the pinned action checkout — so the
decision and the only token-using code both come from the protected ref, never from
the caller's checkout. Missing, unreadable or not-ok capacity -> hosted.
--github-output FILE appends `runner=` / `target=` lines for Actions.
An unknown mode is treated as off. A decision line goes to stderr (no secrets).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional, Union

HOSTED = "ubuntu-24.04"
MODES = ("off", "hybrid", "fleet-only")
CLASSES = ("std", "heavy")


def fleet_labels(cls: str) -> List[str]:
    return ["self-hosted", "Linux", "X64", "fleet", f"fleet-{cls}"]


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() in ("true", "1", "yes")


def decide(mode: str, cls: str, jobs_needed: int, capacity: Optional[Dict[str, Any]],
           spill_ratio: float = 1.0, trusted_source: bool = False,
           repo_private: bool = False) -> Dict[str, Any]:
    mode = mode if mode in MODES else "off"
    cls = cls if cls in CLASSES else "std"
    jobs = max(1, jobs_needed)
    base = {"trusted_source": bool(trusted_source), "repo_private": bool(repo_private)}
    if mode == "off":
        return {**base, "runner": HOSTED, "target": "hosted", "why": "mode=off"}
    if not trusted_source:
        # Fork PRs (and any caller that did not prove a trusted source) never get
        # fleet labels, in any mode. Fail closed.
        return {**base, "runner": HOSTED, "target": "hosted", "why": "untrusted-source"}
    if mode == "fleet-only":
        return {**base, "runner": fleet_labels(cls), "target": "fleet", "why": "mode=fleet-only"}
    if not isinstance(capacity, dict) or capacity.get("ok") is not True:
        return {**base, "runner": HOSTED, "target": "hosted", "why": "capacity-unavailable"}
    bucket = (capacity.get("per_class") or {}).get(cls)
    idle = bucket.get("idle") if isinstance(bucket, dict) else None
    if not isinstance(idle, int) or isinstance(idle, bool) or idle < 0:
        return {**base, "runner": HOSTED, "target": "hosted", "why": "capacity-invalid"}
    ratio = spill_ratio if isinstance(spill_ratio, (int, float)) and math.isfinite(spill_ratio) else 1.0
    ratio = min(1.0, max(0.0, ratio))
    if idle >= jobs:
        return {**base, "runner": fleet_labels(cls), "target": "fleet", "why": f"idle={idle}>=jobs={jobs}"}
    if idle >= 1 and ratio < 1.0 and idle / jobs >= ratio:
        return {**base, "runner": fleet_labels(cls), "target": "fleet",
                "why": f"spill idle={idle}/jobs={jobs}>={ratio:g}"}
    return {**base, "runner": HOSTED, "target": "hosted", "why": f"idle={idle}<jobs={jobs}"}


def runs_on_json(runner: Union[str, List[str]]) -> str:
    return json.dumps(runner, separators=(",", ":"))


def fetch_capacity(script_dir: str) -> Optional[Dict[str, Any]]:
    """Run the sibling fleet-capacity from `script_dir` (the pinned action checkout).

    Only this pinned code reads FLEET_ROUTE_TOKEN (inherited via the environment).
    Any failure returns None -> the decision falls back to hosted.
    """
    try:
        proc = subprocess.run([sys.executable, os.path.join(script_dir, "fleet-capacity"), "--soft"],
                              capture_output=True, text=True, timeout=120)
        data = json.loads(proc.stdout)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="fleet_route")
    p.add_argument("--mode", default="off")
    p.add_argument("--class", dest="cls", default="std")
    p.add_argument("--jobs-needed", default="1")
    p.add_argument("--capacity")
    p.add_argument("--spill-ratio", default="1.0")
    p.add_argument("--trusted-source", default="false")
    p.add_argument("--repo-private", default="false")
    p.add_argument("--fetch-capacity", action="store_true",
                   help="hybrid: run the sibling fleet-capacity from this script's directory")
    p.add_argument("--github-output", help="append runner=/target= lines to this Actions output file")
    args = p.parse_args(argv)
    try:
        jobs = int(args.jobs_needed)
    except ValueError:
        jobs = 1
    try:
        ratio = float(args.spill_ratio)
    except ValueError:
        ratio = 1.0
    mode = args.mode.strip().lower()
    capacity = None
    if args.capacity:
        try:
            with open(args.capacity, encoding="utf-8") as fh:
                capacity = json.load(fh)
        except (OSError, ValueError):
            capacity = None
    elif args.fetch_capacity and mode == "hybrid":
        capacity = fetch_capacity(os.path.dirname(os.path.abspath(__file__)))
    d = decide(mode, args.cls.strip().lower(), jobs, capacity, ratio,
               trusted_source=_as_bool(args.trusted_source), repo_private=_as_bool(args.repo_private))
    print(f"fleet-route: target={d['target']} why={d['why']}", file=sys.stderr)
    runner_json = runs_on_json(d["runner"])
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as fh:
            fh.write(f"runner={runner_json}\ntarget={d['target']}\n")
    print(runner_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
