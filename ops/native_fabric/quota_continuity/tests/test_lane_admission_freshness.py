"""Actual admission locks and leases; no provider, host or live lane is used."""
import fcntl
import json
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "candidate/lane_runtime.py"

CHILD = r"""
import fcntl
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch

source, root, key, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
spec = importlib.util.spec_from_file_location("freshness_fixture_runtime", source)
runtime = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runtime
spec.loader.exec_module(runtime)
original_flock = fcntl.flock
def observed_flock(fd, operation):
    if operation == fcntl.LOCK_EX:
        print("WAITING", flush=True)
    return original_flock(fd, operation)
def observed_load():
    value = float((root / "load").read_text())
    with (root / (key + ".samples")).open("a") as samples:
        samples.write(json.dumps(value) + "\n")
    return value, value, value
lease = None
try:
    with patch.object(runtime.fcntl, "flock", observed_flock), \
         patch.object(runtime.os, "getloadavg", observed_load):
        kwargs = {"load1": 0.0} if mode == "explicit" else {}
        try:
            lease = runtime.LaneLease.acquire(
                root / "active", key=key, label=key, env={"LANE_MAX_ACTIVE": "1"},
                max_active=1, cpu_count=1, load_ratio_limit=0.7, **kwargs)
            result = {"allowed": True, "snapshot": lease.snapshot.public_dict()}
        except runtime.LaneAdmissionRefused as exc:
            result = {"allowed": False, "snapshot": exc.snapshot.public_dict()}
        print("RESULT " + json.dumps(result), flush=True)
        if lease is not None:
            sys.stdin.readline()
finally:
    if lease is not None:
        lease.release()
"""


class AdmissionFreshness(unittest.TestCase):
    source = SOURCE

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.active = self.root / "active"
        self.active.mkdir()
        self.load = self.root / "load"
        self.load.write_text("0")
        self.lock = (self.active / ".admission.lock").open("w")
        self.addCleanup(self.lock.close)
        fcntl.flock(self.lock, fcntl.LOCK_EX)
        self.addCleanup(fcntl.flock, self.lock, fcntl.LOCK_UN)
        self.children = []
        self.addCleanup(self.finish_children)

    def finish_children(self):
        for proc in self.children:
            if proc.poll() is None:
                try:
                    proc.communicate("\n", timeout=3)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try:
                        proc.communicate(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.communicate(timeout=2)
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()

    def line(self, proc):
        ready, _, _ = select.select([proc.stdout], [], [], 5)
        self.assertTrue(ready, "fixture child did not reach the expected physical-lock boundary")
        line = proc.stdout.readline()
        if not line:
            _, error = proc.communicate(timeout=2)
            self.fail("fixture child exited before admission: " + error[-3000:])
        return line.rstrip("\n")

    def start(self, key, mode="default"):
        proc = subprocess.Popen(
            [sys.executable, "-u", "-c", CHILD, str(self.source), str(self.root), key, mode],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True)
        self.children.append(proc)
        self.assertEqual(self.line(proc), "WAITING")
        return proc

    def result(self, proc):
        line = self.line(proc)
        self.assertTrue(line.startswith("RESULT "), line)
        result = json.loads(line.removeprefix("RESULT "))
        out, err = proc.communicate("\n", timeout=5)
        self.assertEqual(proc.returncode, 0, err)
        self.assertEqual(out, "")
        return result

    def samples(self, key):
        path = self.root / (key + ".samples")
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_rising_load_while_waiting_refuses_without_a_marker(self):
        proc = self.start("rising")
        sampled_before_lock = self.samples("rising")
        self.load.write_text("0.7")
        fcntl.flock(self.lock, fcntl.LOCK_UN)
        result = self.result(proc)
        self.assertFalse(result["allowed"], result)
        self.assertEqual(result["snapshot"]["reasons"], ["host_load_at_or_above_limit"])
        self.assertEqual(result["snapshot"]["load1"], 0.7)
        self.assertEqual(sampled_before_lock, [])
        self.assertEqual(self.samples("rising"), [0.7])
        self.assertFalse((self.active / "rising").exists())

    def test_falling_load_while_waiting_uses_the_current_sample(self):
        self.load.write_text("1.0")
        proc = self.start("falling")
        self.load.write_text("0.0")
        fcntl.flock(self.lock, fcntl.LOCK_UN)
        result = self.result(proc)
        self.assertTrue(result["allowed"], result)
        self.assertEqual(self.samples("falling"), [0.0])
        self.assertFalse((self.active / "falling").exists())

    def test_explicit_load_fixture_does_not_probe_live_load(self):
        self.load.write_text("1.0")
        proc = self.start("explicit", "explicit")
        fcntl.flock(self.lock, fcntl.LOCK_UN)
        result = self.result(proc)
        self.assertTrue(result["allowed"], result)
        self.assertEqual(self.samples("explicit"), [])

    def test_two_waiting_processes_cannot_both_take_one_free_slot(self):
        children = [self.start(key) for key in ("first", "second")]
        fcntl.flock(self.lock, fcntl.LOCK_UN)
        results = []
        # Keep any winning lease open until BOTH decisions have been observed.
        for proc in children:
            line = self.line(proc)
            self.assertTrue(line.startswith("RESULT "), line)
            results.append(json.loads(line.removeprefix("RESULT ")))
        self.assertEqual(sum(result["allowed"] for result in results), 1, results)
        refused = next(result for result in results if not result["allowed"])
        self.assertIn("active_lane_limit_reached", refused["snapshot"]["reasons"])
        for proc in children:
            _, err = proc.communicate("\n", timeout=5)
            self.assertEqual(proc.returncode, 0, err)
        self.assertFalse((self.active / "first").exists())
        self.assertFalse((self.active / "second").exists())


class BoundAdmissionFreshness(AdmissionFreshness):
    # The original attended backend packages the same physical admission owner.
    source = ROOT.parents[2] / "integrations/session_bridge/bound_launch_capture/runtime/lane_runtime.py"

    def test_packaged_forward_delta_preserves_frozen_capture_inputs(self):
        import hashlib
        record = json.loads(self.source.with_name("PROVENANCE.json").read_text())["inputs"]["lane_runtime.py"]
        forward = record["admission_freshness_forward"]
        self.assertEqual(forward["preimage_packaged_sha256"],
                         "cfb18bd9381fae4af1d13a257a8fa5986d903571f64b2aa5dc900439759e9b91")
        current = self.source.read_bytes()
        self.assertEqual(hashlib.sha256(current).hexdigest(), record["packaged_sha256"])
        self.assertEqual(record["packaged_sha256"], forward["postimage_packaged_sha256"])
        patch = ROOT.parents[2] / forward["patch"]
        self.assertEqual(hashlib.sha256(patch.read_bytes()).hexdigest(), forward["patch_sha256"])
        target = self.root / "lane_runtime.py"
        target.write_bytes(current)
        def apply(*options):
            result = subprocess.run(["git", "apply", "--unidiff-zero", *options, str(patch)],
                cwd=self.root, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
        apply("--reverse", "--check")
        apply("--reverse")
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),
                         forward["preimage_packaged_sha256"])
        apply("--check")
        apply()
        self.assertEqual(target.read_bytes(), current)
        self.assertEqual(record["base_sha256"], "d36860ea8036ed5ec733a47c709a477c851fee95dddbae23c8e2214dc308b77e")
        self.assertEqual(record["patch_sha256"], "664002d7309779e69cd5f1b3e6a260215f1247526c813824e7e8f5897c8457be")
        self.assertEqual(record["materialized_candidate_sha256"],
                         "54d7ba3e6164cf05ef90ff1e169b0fef716655e759d4076b6d218e1e4d9bf096")
