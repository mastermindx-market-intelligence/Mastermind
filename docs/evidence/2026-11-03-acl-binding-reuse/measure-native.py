#!/usr/bin/env python3
"""Finite native ACL comparison on an owned empty disposable fixture only."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import platform
import pwd
import statistics
import subprocess
import sys
import tempfile
import time

BASELINE = "aad443d4d712cc2483a912b6371779bd56f05ee08bc07bff9b3c3008ab0b52e7"
CANDIDATE = "4a9aa64a34cbc84601fbfd5ea68b9792eb1c5558116c48d52c797ad0c83758a5"
ITERATIONS, PAIRS = 512, 5


def load(name, expected):
    path = Path(__file__).parent / (name + "_fs_security.py")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    spec = importlib.util.spec_from_file_location("mmos_acl_" + name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-uid", type=int, required=True)
    args = parser.parse_args()
    assert args.expected_uid > 0
    assert sys.platform == "darwin" and os.getuid() == os.geteuid() == args.expected_uid
    assert platform.python_version() == "3.12.10"
    modules = {"baseline": load("baseline", BASELINE), "candidate": load("candidate", CANDIDATE)}
    rows = []
    with tempfile.TemporaryDirectory(prefix="empty-fixture-", dir=Path(__file__).parent) as directory:
        fixture = Path(directory) / "empty"
        fixture.touch(mode=0o600, exist_ok=False)
        assert fixture.stat().st_size == 0 and fixture.stat().st_uid == os.getuid()
        for module in modules.values():
            assert module.has_macos_acl(fixture) is False
        account = pwd.getpwuid(os.getuid()).pw_name
        subprocess.run(["/bin/chmod", "+a", "user:" + account + " allow read", str(fixture)], check=True,
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for module in modules.values():
            assert module.has_macos_acl(fixture) is True
        subprocess.run(["/bin/chmod", "-N", str(fixture)], check=True,
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for module in modules.values():
            assert module.has_macos_acl(fixture) is False
        fd = os.open(fixture, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            identity = os.fstat(fd)
            for mode in ("path_owned", "held_descriptor"):
                kwargs = {} if mode == "path_owned" else {"descriptor": fd, "expected_identity": identity}
                for module in modules.values():
                    for _ in range(4):
                        assert module.has_macos_acl(fixture, **kwargs) is False
                for pair in range(PAIRS):
                    order = ("baseline", "candidate") if pair % 2 == 0 else ("candidate", "baseline")
                    for name in order:
                        observe = modules[name].has_macos_acl
                        wall, cpu = time.perf_counter_ns(), time.process_time_ns()
                        for _ in range(ITERATIONS):
                            assert observe(fixture, **kwargs) is False
                        rows.append({"mode": mode, "pair": pair, "candidate": name,
                                     "cpu_ns": time.process_time_ns() - cpu,
                                     "wall_ns": time.perf_counter_ns() - wall,
                                     "observations": ITERATIONS})
            assert os.fstat(fd).st_ino == identity.st_ino
        finally:
            os.close(fd)
    summaries = {}
    for mode in ("path_owned", "held_descriptor"):
        item = {}
        for clock in ("cpu_ns", "wall_ns"):
            medians = {name: statistics.median(row[clock] / ITERATIONS for row in rows
                if row["mode"] == mode and row["candidate"] == name) for name in modules}
            item[clock + "_per_observation"] = medians
            item[clock + "_baseline_over_candidate"] = medians["baseline"] / medians["candidate"]
        summaries[mode] = item
    result = {"schema": "mastermind.acl_binding_microbenchmark.v1", "uid": os.getuid(),
              "python": platform.python_version(), "executable": sys.executable,
              "machine": platform.machine(), "baseline_sha256": BASELINE, "candidate_sha256": CANDIDATE,
              "native_acl_transition": ["absent", "present", "absent"], "transition_passed": True,
              "fixture_removed": True, "iterations_per_sample": ITERATIONS, "pairs_per_mode": PAIRS,
              "samples": rows, "summaries": summaries,
              "scope": "isolated observer calls; no installed acceptance speedup claimed"}
    target = Path(__file__).parent / "result.json"
    with target.open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps({"result_path": str(target), "result_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                      "transition_passed": True, "summaries": summaries}, sort_keys=True))


if __name__ == "__main__":
    main()
