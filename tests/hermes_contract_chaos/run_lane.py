#!/usr/bin/env python3
"""Run H24 source-only conformance with exclusive, fail-closed evidence receipts.

Uses an existing pytest environment; performs no installation or host activation.
Report ownership uses the OS file lock only, never a worker/runtime lifecycle.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LANES = {
    "concurrency": (HERE / "test_h24_concurrency.py",),
    "failures": (HERE / "test_h24_failures.py", HERE / "test_h24_lane_receipts.py"),
}


class ReportBusy(RuntimeError):
    pass


@contextmanager
def report_lease(report):
    # Keep the lock inode: unlinking it could let a third process lock a second
    # inode while an earlier holder still owns the original one.
    flags = os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
    fd = os.open(str(report) + ".lock", flags, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ReportBusy() from None
        yield
    finally:
        os.close(fd)


def source_snapshot():
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(HERE.glob("*.py"))}


def validate_receipts(junit, manifest, invocation_id, expected_files, pytest_exit_code):
    summary, execution, errors = {}, {}, []
    try:
        suites = ET.parse(junit).getroot()
        summary = {key: sum(int(suite.attrib[key]) for suite in suites.iter("testsuite"))
                   for key in ("tests", "failures", "errors", "skipped")}
        if any(value < 0 for value in summary.values()):
            raise ValueError()
    except (OSError, ET.ParseError, ValueError, KeyError):
        errors.append("JUNIT_UNAVAILABLE_OR_INVALID")
    try:
        raw = json.loads(manifest.read_text())
        if (raw["schema"] != "mastermind.h24_pytest_execution.v1"
                or raw["invocation_id"] != invocation_id
                or raw["pytest_exit_code"] != pytest_exit_code):
            raise ValueError()
        collected, deselected, reports = raw["collected"], raw["deselected"], raw["reports"]
        if (not isinstance(collected, list) or not all(isinstance(node, str) for node in collected)
                or len(collected) != len(set(collected)) or not isinstance(deselected, list)
                or not isinstance(reports, list)):
            raise ValueError()
        stages = {node: {} for node in collected}
        for item in reports:
            node, when, outcome = item["node_id"], item["when"], item["outcome"]
            if (node not in stages or when not in {"setup", "call", "teardown"}
                    or when in stages[node] or outcome not in {"passed", "failed", "skipped"}):
                raise ValueError()
            stages[node][when] = outcome
        completed = sum(set(value) == {"setup", "call", "teardown"} for value in stages.values())
        execution = {"collected": len(collected), "completed": completed,
                     "deselected": len(deselected),
                     "node_ids_sha256": hashlib.sha256(json.dumps(collected).encode()).hexdigest()}
        if (not collected or deselected or completed != len(collected)
                or {node.split("::", 1)[0] for node in collected} != set(expected_files)):
            errors.append("EXECUTION_INCOMPLETE")
        if any(outcome != "passed" for stages_for_node in stages.values() for outcome in stages_for_node.values()):
            errors.append("EXECUTION_NOT_ALL_PASSED")
        if summary.get("tests") != len(collected):
            errors.append("JUNIT_EXECUTION_COUNT_MISMATCH")
        if any(summary.get(key, 0) for key in ("failures", "errors", "skipped")):
            errors.append("JUNIT_NOT_ALL_PASSED")
    except (OSError, ValueError, KeyError, TypeError):
        errors.append("EXECUTION_MANIFEST_UNAVAILABLE_OR_INVALID")
    return summary, execution, sorted(set(errors))


def execute(args, seeds, report):
    selected = [path for lane in LANES.values() for path in lane] if args.lane == "all" else list(LANES[args.lane])
    junit = report.with_suffix(".junit.xml")
    manifest = report.with_suffix(".execution.json")
    for old in (report, junit, manifest):
        old.unlink(missing_ok=True)
    invocation_id = uuid.uuid4().hex
    started_at = datetime.now(timezone.utc).isoformat()
    before = source_snapshot()
    with tempfile.TemporaryDirectory(prefix=".h24-invocation-", dir=report.parent) as temporary:
        directory = Path(temporary)
        fresh_junit, fresh_manifest = directory / "junit.xml", directory / "execution.json"
        command = [sys.executable, "-m", "pytest", "-o", "addopts=", "-q",
                   "--confcutdir=" + str(HERE), "--tb=short", "--durations=10",
                   "--junitxml=" + str(fresh_junit), *map(str, selected),
                   *(f"--chaos-seed={seed}" for seed in seeds)]
        env = {key: value for key, value in os.environ.items()
               if key not in {"PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_CURRENT_TEST"}}
        env.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONNOUSERSITE="1",
                   PYTHONPATH=os.pathsep.join((str(ROOT), str(ROOT / "tests"))), PYTHONHASHSEED="0",
                   H24_EXECUTION_MANIFEST=str(fresh_manifest), H24_INVOCATION_ID=invocation_id)
        started = time.monotonic()
        invocation_error = None
        pytest_exit_code = None
        try:
            pytest_exit_code = subprocess.run(command, cwd=ROOT, env=env, check=False,
                                              timeout=args.timeout_seconds).returncode
            exit_code = pytest_exit_code
        except subprocess.TimeoutExpired:
            exit_code, invocation_error = 124, "PYTEST_TIMEOUT"
        except OSError as error:
            exit_code, invocation_error = 127, type(error).__name__
        elapsed = time.monotonic() - started
        summary, execution, errors = validate_receipts(fresh_junit, fresh_manifest, invocation_id,
            [str(path.relative_to(ROOT)) for path in selected], pytest_exit_code)
        after = source_snapshot()
        if after != before:
            errors.append("SOURCE_CHANGED_DURING_EXECUTION")
        if errors:
            exit_code = exit_code or 2
        result = {
            "schema": "mastermind.h24_chaos_timing.v2", "invocation_id": invocation_id,
            "lane": args.lane, "seeds": seeds, "python": platform.python_version(),
            "platform": platform.system(), "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(elapsed, 3), "budget_seconds": args.budget_seconds,
            "within_budget": elapsed <= args.budget_seconds, "timeout_seconds": args.timeout_seconds,
            "exit_code": exit_code, "pytest_exit_code": pytest_exit_code,
            "qualification": "PASS" if exit_code == 0 else "NOT_QUALIFIED",
            "pytest_summary": summary, "execution": execution, "receipt_errors": errors,
            "invocation_error": invocation_error, "tests_sha256": before,
            "source_unchanged": before == after, "command": command,
            "junit": str(junit), "execution_manifest": str(manifest),
            "scope": "OFFLINE_SOURCE_CONFORMANCE_ONLY", "native_service_qualified": False,
        }
        for key, fresh, final in (("junit_sha256", fresh_junit, junit),
                                  ("execution_manifest_sha256", fresh_manifest, manifest)):
            if fresh.is_file():
                result[key] = hashlib.sha256(fresh.read_bytes()).hexdigest()
                os.replace(fresh, final)
        pending = directory / "report.json"
        pending.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        os.replace(pending, report)
    print(json.dumps({key: result[key] for key in ("lane", "seeds", "elapsed_seconds",
          "within_budget", "exit_code", "qualification", "pytest_summary", "receipt_errors", "scope")}, sort_keys=True))
    return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", choices=(*LANES, "all"), default="all")
    parser.add_argument("--seeds", default="0,1,0x2410")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--budget-seconds", type=float, default=60.0)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    args = parser.parse_args()
    try:
        seeds = [int(value.strip(), 0) for value in args.seeds.split(",")]
    except ValueError:
        parser.error("seeds must be comma-separated integers")
    if not 1 <= len(seeds) <= 16 or len(set(seeds)) != len(seeds):
        parser.error("provide 1..16 distinct deterministic seeds")
    if not 0 < args.budget_seconds <= 300 or not 0 < args.timeout_seconds <= 240:
        parser.error("budget must be within (0,300] and timeout within (0,240] seconds")
    report = args.report.resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    try:
        with report_lease(report):
            return execute(args, seeds, report)
    except ReportBusy:
        print(json.dumps({"exit_code": 75, "qualification": "NOT_QUALIFIED",
                          "invocation_error": "REPORT_BUSY"}, sort_keys=True))
        return 75


if __name__ == "__main__":
    raise SystemExit(main())
