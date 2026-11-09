"""Offline W1 D-G7B-4 / D-G7B-5 tests. The SSH executable is a local fixture; no host access."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest


DRIVER = Path(__file__).with_name("install_w1.sh")
BASH = shutil.which("bash")
FAKE_SSH = r'''
import contextlib, importlib.metadata, io, json, os, shlex, subprocess, sys
from unittest.mock import patch
mode = os.environ.get("W1_TEST_REMOTE_MODE", "pass")
args = shlex.split(sys.argv[-1])
assert args[:6] == ["timeout", "--signal=KILL", "15s", "/opt/mastermind/.venv/bin/python", "-I", "-B"]
assert args[6] == "-" and len(args) == 8
program = sys.stdin.read()
with open(os.environ["W1_TEST_TRACE"], "a") as f: f.write("probe\n")
if mode == "exit": sys.exit(124)
if mode == "malformed": print("not-json"); sys.exit(0)
if mode == "oversize": print("x" * 8193); sys.exit(0)
out = io.StringIO()
exe = "/wrong/python" if mode == "interpreter" else "/opt/mastermind/.venv/bin/python"
unit = "{ path=/wrong/uvicorn ; argv[]=ignored ; }" if mode == "service" else "{ path=/opt/mastermind/.venv/bin/uvicorn ; argv[]=ignored ; }"
version = "4.25.0" if mode == "version" else "4.26.0"
def metadata(name):
    assert name == "jsonschema"
    if mode == "missing": raise importlib.metadata.PackageNotFoundError(name)
    return version
def show(argv, **kwargs):
    assert argv == ["systemctl", "show", "mastermind.service", "-p", "ExecStart", "--value"]
    assert kwargs == {"text": True, "timeout": 5}
    if mode == "systemctl_timeout": raise subprocess.TimeoutExpired(argv, 5)
    return unit
with contextlib.ExitStack() as stack:
    stack.enter_context(patch.object(sys, "argv", ["-", args[7]]))
    stack.enter_context(patch.object(sys, "executable", exe))
    stack.enter_context(patch("importlib.metadata.version", metadata))
    stack.enter_context(patch("subprocess.check_output", show))
    if mode in ("invalid_accepted", "valid_rejected"):
        stack.enter_context(patch("jsonschema.Draft202012Validator.is_valid", return_value=mode == "invalid_accepted"))
    if mode == "format_ignored": stack.enter_context(patch("jsonschema.FormatChecker", return_value=None))
    with contextlib.redirect_stdout(out): exec(compile(program, "<fixed-compatibility-probe>", "exec"), {})
result = json.loads(out.getvalue())
if mode in ("nonce", "attempt", "target", "phase"):
    result["binding"][mode] = "foreign"
elif mode == "result_shape": result["extra"] = True
elif mode == "result_version": result["version"] = "4.25.0"
elif mode == "result_bool": result["valid"] = "true"
elif mode == "result_int": result["valid"] = 1
elif mode == "result_count": result["invalid_rejected"] = 6.0
print(json.dumps(result))
'''


class JsonschemaConditionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="w1-condition-")
        self.root = Path(self.temp.name)
        self.ev = self.root / "attempt with spaces"
        for rel in ("identity/pre", "identity/prelaunch", "identity/post", "logs", "gates"):
            (self.ev / rel).mkdir(parents=True, exist_ok=True)
        self.dists = self.ev / "identity/pre/dists.txt"
        self.dists.write_text("anthropic==1.0\nclaude-agent-sdk==0.1\njsonschema==4.26.0\n")
        self.fresh = self.root / "fresh-dists.txt"
        self.fresh.write_bytes(self.dists.read_bytes())
        self.trace = self.root / "trace"
        self.ssh = self.root / "fake-ssh"
        self.ssh.write_text("#!" + sys.executable + "\n" + FAKE_SSH)
        self.ssh.chmod(0o755)
        self.env = {**os.environ, "W1_TEST_TRACE": str(self.trace)}
        self.target = "1" * 40
        self.prefix = "\n".join([
            "source " + shlex.quote(str(DRIVER)),
            "EV=" + shlex.quote(str(self.ev)),
            "SHA=" + self.target, "WT=fixture", "G7B_MODE=D-G7B-4", "T2_MODE=equal",
            "PY=" + shlex.quote(sys.executable),
            "VPS=(" + shlex.quote(str(self.ssh)) + " fixture-host)",
            "g7b_jsonschema_pair() { return 0; }", "g7b_d5_manifest() { return 1; }",
        ]) + "\n"

    def tearDown(self):
        self.temp.cleanup()

    def run_shell(self, body, *, mode="pass", before=""):
        return subprocess.run([BASH, "--noprofile", "--norc", "-c", self.prefix + before + body],
                              env={**self.env, "W1_TEST_REMOTE_MODE": mode}, capture_output=True, text=True, timeout=12)

    def condition(self, phase="pre", *, mode="pass", before=""):
        dist = self.ev / f"identity/{phase}/dists.txt"
        if phase != "pre": dist.write_bytes(self.fresh.read_bytes())
        proof = self.ev / f"identity/{phase}/jsonschema.compatibility.json"
        call = "t2_jsonschema_condition " + " ".join(map(shlex.quote, (phase, str(dist), str(proof))))
        return self.run_shell(call, mode=mode, before=before), proof

    def establish_pre(self):
        result, proof = self.condition()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return proof

    def test_real_validator_features_and_fresh_phase_bindings(self):
        pre = json.loads(self.establish_pre().read_text())
        self.assertEqual(pre["driver_sha256"], hashlib.sha256(DRIVER.read_bytes()).hexdigest())
        self.assertEqual(pre["result"]["invalid_rejected"], 6)
        nonces = {pre["nonce"]}
        for phase in ("prelaunch", "post"):
            result, proof = self.condition(phase)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            body = json.loads(proof.read_text())
            self.assertEqual(body["phase"], phase)
            self.assertNotIn(body["nonce"], nonces)
            nonces.add(body["nonce"])

    def test_missing_or_wrong_distribution_refuses_without_contact(self):
        for content in ("other==1\n", "jsonschema==4.25.0\n", "jsonschema==4.26.0\njsonschema==4.26.0\n"):
            with self.subTest(content=content):
                self.dists.write_text(content)
                result, proof = self.condition()
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(proof.exists())
                self.assertFalse(self.trace.exists())

    def test_remote_failures_never_create_proof(self):
        for mode in ("exit", "malformed", "oversize", "interpreter", "service", "version", "missing",
                     "systemctl_timeout", "invalid_accepted", "valid_rejected", "format_ignored", "nonce",
                     "attempt", "target", "phase", "result_shape", "result_version", "result_bool", "result_int", "result_count"):
            with self.subTest(mode=mode):
                result, proof = self.condition(mode=mode)
                self.assertNotEqual(result.returncode, 0, mode)
                self.assertFalse(proof.exists(), mode)

    def test_missing_mode_cannot_downgrade_exact_source(self):
        result, proof = self.condition(before="unset G7B_MODE\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(proof.exists())
        self.assertFalse(self.trace.exists())

    def test_wrong_mode_source_or_t2_refuses(self):
        for before in ("G7B_MODE=legacy\n", "T2_MODE=floor_pending\n",
                       "g7b_jsonschema_pair() { return 1; }\n", "g7b_jsonschema_pair() { return 2; }\n"):
            with self.subTest(before=before):
                result, proof = self.condition(before=before)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(proof.exists())

    def test_legacy_case_does_not_add_a_runtime_dependency(self):
        result, proof = self.condition(before="unset G7B_MODE\ng7b_jsonschema_pair() { return 1; }\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(proof.exists())
        self.assertFalse(self.trace.exists())

    D5 = "G7B_MODE=D-G7B-5\ng7b_jsonschema_pair() { return 1; }\ng7b_d5_manifest() { return 0; }\n"

    def test_d5_ruling_binds_every_phase(self):
        result, proof = self.condition(before=self.D5)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(proof.read_text())["ruling"], "D-G7B-5")
        for phase in ("prelaunch", "post"):
            result, proof = self.condition(phase, before=self.D5)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(json.loads(proof.read_text())["ruling"], "D-G7B-5")

    def test_d5_source_with_wrong_missing_or_unreadable_state_refuses(self):
        for before in (self.D5 + "G7B_MODE=D-G7B-4\n", self.D5 + "unset G7B_MODE\n", self.D5 + "G7B_MODE=legacy\n",
                       self.D5 + "T2_MODE=floor_pending\n", self.D5 + "g7b_d5_manifest() { return 2; }\n"):
            with self.subTest(before=before):
                result, proof = self.condition(before=before)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(proof.exists())
                self.assertFalse(self.trace.exists())

    def test_cross_ruling_baseline_refuses(self):
        self.establish_pre()
        result, proof = self.condition("prelaunch", before=self.D5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("D-G7B-5 runtime condition REFUSED", result.stderr)
        self.assertFalse(proof.exists())

    def test_missing_prior_proof_refuses_without_contact(self):
        result, proof = self.condition("prelaunch")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(proof.exists())
        self.assertFalse(self.trace.exists())

    def test_copied_or_inconsistent_baseline_refuses(self):
        path = self.establish_pre()
        original = json.loads(path.read_text())
        for key in ("schema", "ruling", "attempt", "target", "phase", "probe_sha256", "driver_sha256", "distributions_sha256"):
            with self.subTest(key=key):
                changed = dict(original); changed[key] = "foreign"
                path.write_text(json.dumps(changed))
                result, proof = self.condition("prelaunch")
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(proof.exists())

    def test_prelaunch_distribution_drift_refuses_before_launch(self):
        self.establish_pre()
        self.fresh.write_text(self.fresh.read_text() + "new-dist==1\n")
        result = self.run_s3()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("T2 prelaunch venv drift", result.stdout)
        self.assertFalse((self.ev / "logs/deploy.started").exists())
        self.assertNotIn("launch", self.trace.read_text())

    def run_s3(self, *, mode="pass", clock="100"):
        for gate in ("PRE", "G7"): (self.ev / f"gates/{gate}.PASS").touch()
        trace = shlex.quote(str(self.trace))
        body = "\n".join([
            "load() { :; }; env_guard() { :; }; W_LAST_START=200",
            "gates_all() { echo gates >> " + trace + "; }",
            "host_now() { echo clock >> " + trace + "; echo " + clock + "; }",
            "dists_read() { cat " + shlex.quote(str(self.fresh)) + ' > "$1"; }',
            "launch_detached() { echo launch >> " + trace + '; echo 123 > "$EV/logs/deploy.pid"; }',
            "s3",
        ])
        return self.run_shell(body, mode=mode)

    def test_current_compatibility_failure_blocks_s3_even_with_pre_proof(self):
        self.establish_pre()
        result = self.run_s3(mode="format_ignored")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.ev / "logs/deploy.started").exists())
        self.assertNotIn("launch", self.trace.read_text())

    def test_s3_rechecks_clock_after_condition_and_launches_once(self):
        self.establish_pre(); self.trace.write_text("")
        result = self.run_s3()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.trace.read_text().splitlines(), ["probe", "gates", "clock", "launch"])
        self.assertTrue((self.ev / "logs/deploy.started").exists())
        result = self.run_s3()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.trace.read_text().splitlines().count("launch"), 1)

    def test_expired_window_after_condition_never_launches(self):
        self.establish_pre(); self.trace.write_text("")
        result = self.run_s3(clock="200")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.trace.read_text().splitlines(), ["probe", "gates", "clock"])
        self.assertFalse((self.ev / "logs/deploy.started").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
