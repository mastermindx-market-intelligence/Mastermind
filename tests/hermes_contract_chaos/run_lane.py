#!/usr/bin/env python3
"""Run only H24 offline tests and retain an honest timing/exit-code receipt.

Uses an already available pytest environment. No dependency, service, model,
credential, provider or runtime installation is performed by this runner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LANES = {
    "concurrency": HERE / "test_h24_concurrency.py",
    "failures": HERE / "test_h24_failures.py",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", choices=(*LANES, "all"), default="all")
    parser.add_argument("--seeds", default="0,1,0x2410")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--budget-seconds", type=float, default=60.0)
    args = parser.parse_args()
    try:
        seeds = [int(value.strip(), 0) for value in args.seeds.split(",")]
    except ValueError:
        parser.error("seeds must be comma-separated integers")
    if not 1 <= len(seeds) <= 16 or len(set(seeds)) != len(seeds):
        parser.error("provide 1..16 distinct deterministic seeds")
    if not 0 < args.budget_seconds <= 300:
        parser.error("budget must be positive and no greater than 300 seconds")
    selected = list(LANES.values()) if args.lane == "all" else [LANES[args.lane]]
    report = args.report.resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    junit = report.with_suffix(".junit.xml")
    # A repeated local invocation must never attach an earlier passing receipt
    # to a pytest process that did not produce its own report.
    report.unlink(missing_ok=True)
    junit.unlink(missing_ok=True)
    command = [sys.executable, "-m", "pytest", "-o", "addopts=", "-q",
               "--confcutdir=" + str(HERE), "--tb=short", "--durations=10",
               "--junitxml=" + str(junit), *map(str, selected),
               *(f"--chaos-seed={seed}" for seed in seeds)]
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
               PYTHONPATH=os.pathsep.join((str(ROOT), str(ROOT / "tests"))),
               PYTHONHASHSEED="0")
    started = time.monotonic()
    invocation_error = None
    try:
        exit_code = subprocess.run(command, cwd=ROOT, env=env, check=False).returncode
    except OSError as error:
        exit_code = 127
        invocation_error = type(error).__name__  # No secret-bearing exception text.
    elapsed = time.monotonic() - started
    summary = {}
    try:
        suites = ET.parse(junit).getroot()
        summary = {key: sum(int(suite.get(key, "0")) for suite in suites.iter("testsuite"))
                   for key in ("tests", "failures", "errors", "skipped")}
    except (OSError, ET.ParseError, ValueError) as error:
        invocation_error = invocation_error or type(error).__name__
        exit_code = exit_code or 2
    result = {
        "schema": "mastermind.h24_chaos_timing.v1",
        "lane": args.lane, "seeds": seeds, "python": platform.python_version(),
        "platform": platform.system(), "elapsed_seconds": round(elapsed, 3),
        "budget_seconds": args.budget_seconds, "within_budget": elapsed <= args.budget_seconds,
        "exit_code": exit_code, "pytest_summary": summary,
        "invocation_error": invocation_error,
        "tests_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in sorted(HERE.glob("*.py"))},
        "command": command, "junit": str(junit),
        "scope": "OFFLINE_SOURCE_CONFORMANCE_ONLY",
        "native_service_qualified": False,
    }
    report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: result[key] for key in ("lane", "seeds", "elapsed_seconds",
          "within_budget", "exit_code", "pytest_summary", "scope")}, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
