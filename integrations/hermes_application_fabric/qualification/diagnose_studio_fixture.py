"""Observe the unchanged disposable Studio test; never repair or replay an owner.

The extra Node preload is an instrumentation difference, not release acceptance.
Its files are outside fixture stdout/stderr, descriptors and implementation files.
"""
from pathlib import Path
import argparse
import ast
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from urllib.parse import urlencode


FIXTURE_BLOB = "41dae1f1e0f29b542137ebf53f01a3e16b7f473d"
TARGET = ("private_service_original_delivery_test.ComposedPreservingMigrationTests."
          "test_composed_preserving_migration_imports_then_observes_once")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("baseline", "single", "suite", "all"), required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    root = package.parents[2]
    start = root / "integrations/studio_direct_mcp"
    fixture = start / "private_service_original_delivery_test.py"
    source = fixture.read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(source)).encode() + b"\0" + source,
                        usedforsecurity=False).hexdigest()
    if blob != FIXTURE_BLOB:
        raise RuntimeError("Disposable diagnostic fixture changed; reconcile its exact source first")
    source_head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    subprocess.run(["git", "-C", str(root), "diff", "--exit-code", "HEAD", "--"],
                   stdout=subprocess.DEVNULL, check=True)
    node = Path(shutil.which("node") or "").resolve()
    if not node.is_file():
        raise RuntimeError("Node control runtime is unavailable")
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    if args.mode == "all":
        subprocess.run([str(node), str(package / "launch_observer_selfcheck.mjs")], check=True)
        results = {}
        for mode in ("baseline", "single", "suite"):
            result = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()),
                                     "--mode", mode, "--output", str(output / mode)], check=False)
            results[mode] = result.returncode
        receipt = {"schema": "mastermind.studio_fixture_diagnostic_contexts.v1", "results": results,
                   "fixture_blob": blob, "source_head": source_head,
                   "python": sys.version.split()[0],
                   "production_effects": False, "release_acceptance": False}
        (output / "result.json").write_text(json.dumps(receipt, sort_keys=True) + "\n")
        print("MMX_STUDIO_DIAGNOSTIC_CONTEXTS " + json.dumps(receipt, sort_keys=True), flush=True)
        return 0 if all(value == 0 for value in results.values()) else 1

    # Extract only the allowed test's driver literal, without importing it early
    # and changing discovery/module-loading order in the full-suite control.
    syntax = ast.parse(source)
    driver = next(ast.literal_eval(item.value) for item in syntax.body
                  if isinstance(item, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == "DRIVER" for target in item.targets))
    driver_digest = hashlib.sha256(driver.encode()).hexdigest()
    observations = []
    unmatched_candidates = []
    original_run = subprocess.run

    def observed_run(command, *positional, **keywords):
        if not isinstance(command, (list, tuple)) or len(command) != 4:
            return original_run(command, *positional, **keywords)
        if not all(isinstance(value, str) for value in command):
            return original_run(command, *positional, **keywords)
        candidate = Path(command[1])
        if (candidate.name != "driver.mjs" or Path(command[2]).name != "original-delivery.mjs"):
            return original_run(command, *positional, **keywords)
        try:
            home = candidate.parent.resolve()
            environment = keywords.get("env")
            matches = (Path(command[0]).is_absolute() and Path(command[0]).resolve() == node
                       and candidate.is_absolute() and isinstance(environment, dict)
                       and environment.get("HOME") == str(home)
                       and home.is_relative_to(Path.home().resolve())
                       and Path(command[3]).resolve().parent == home
                       and Path(command[2]).resolve().is_relative_to(home)
                       and hashlib.sha256(candidate.read_bytes()).hexdigest() == driver_digest)
        except Exception:
            matches = False
        if not matches:
            unmatched_candidates.append("different-driver-or-layout")
            return original_run(command, *positional, **keywords)
        observation = {"instrumented": False, "observer_complete": False,
                       "returncode": None, "reports": [], "observer_error": None}
        observations.append(observation)
        try:
            destination = Path(tempfile.mkdtemp(prefix="driver-", dir=output)).resolve()
        except OSError:
            observation["observer_error"] = "observation-directory-unavailable"
            return original_run(command, *positional, **keywords)
        try:
            observer = (package / "launch_observer.mjs").as_uri() + "?" + urlencode({"output": str(destination)})
            # Preserve argv positions as seen by the script and every original
            # run option/environment/timeout. No retry or exception replacement.
            observation["instrumented"] = True
            try:
                result = original_run([command[0], "--import", observer, *command[1:]], *positional, **keywords)
            except BaseException:
                observation["observer_error"] = "original-run-raised"
                raise
            observation["returncode"] = result.returncode
            try:
                paths = sorted(destination.glob("observer-*.json"))
                if len(paths) > 16 or any(path.stat().st_size > 65536 for path in paths):
                    raise ValueError("Observation bound exceeded")
                reports = [json.loads(path.read_text()) for path in paths]
                if any(report.get("schema") != "mastermind.disposable_launch_observation.v1"
                       or report.get("scope") != "standard-exports-and-childprocess-prototype"
                       or not isinstance(report.get("records"), list)
                       or len(report["records"]) > 64 for report in reports):
                    raise ValueError("Observation schema differs")
                primary = [report for report in reports if report["parentPid"] == os.getpid()]
                observation["reports"] = reports
                observation["observer_complete"] = (len(primary) == 1 and not any(report["dropped"] for report in reports))
                if not observation["observer_complete"]:
                    observation["observer_error"] = "incomplete-observation"
            except Exception:
                observation["observer_error"] = "observation-collection-failed"
            # Even a missing/invalid observer receipt must not replace the
            # original CompletedProcess or its surrounding fixture assertion.
            return result
        finally:
            try:
                shutil.rmtree(destination)
            except OSError:
                observation["observer_complete"] = False
                observation["observer_error"] = "observation-cleanup-failed"

    # Match unittest discovery from the repository, without exposing this
    # diagnostic script directory as another test-module search location.
    sys.path[:] = [str(root), *[entry for entry in sys.path
                               if Path(entry or os.curdir).resolve() not in (package, root, start)]]
    sys.path.insert(0, str(start))
    loader = unittest.TestLoader()
    suite = (loader.loadTestsFromName(TARGET) if args.mode != "suite"
             else loader.discover(str(start), pattern="*_test.py"))
    interception = (contextlib.nullcontext() if args.mode == "baseline"
                    else mock.patch.object(subprocess, "run", observed_run))
    with interception:
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    receipt = {"schema": "mastermind.studio_fixture_diagnostic.v1", "mode": args.mode,
               "fixture_blob": blob, "source_head": source_head,
               "python": sys.version.split()[0],
               "tests": result.testsRun, "failures": len(result.failures),
               "errors": len(result.errors), "skipped": len(result.skipped),
               "instrumented": args.mode != "baseline",
               "driver_interceptions": sum(item["instrumented"] for item in observations),
               "unmatched_candidates": len(unmatched_candidates), "observations": observations,
               "implementation_modified": False, "production_effects": False, "release_acceptance": False}
    (output / "result.json").write_text(json.dumps(receipt, sort_keys=True) + "\n")
    print("MMX_STUDIO_DIAGNOSTIC " + json.dumps(receipt, sort_keys=True), flush=True)
    expected_interceptions = 0 if args.mode == "baseline" else 1
    return 0 if (result.wasSuccessful() and result.testsRun and not result.skipped
                 and len(observations) == expected_interceptions
                 and all(item["instrumented"] and item["observer_complete"] for item in observations)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
