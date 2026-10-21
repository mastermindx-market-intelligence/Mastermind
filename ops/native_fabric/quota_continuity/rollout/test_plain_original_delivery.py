#!/usr/bin/env python3
"""Inert end-to-end proof for the forward-only plain original-delivery repair.

Exercises the real producer log binding (remote_sub_helpers.py launch-binding),
the real read-only collector (original_delivery_collector.py collect /
read_collection) and the exact generated remote reader code, against inert
fixture directories. No SSH, lease, provider, ledger or lifecycle effect: the
only substituted carriers are the ssh binary (a local shim that runs the
generated reader verbatim against a fixture account home) and the account-home
resolution seam, mirroring the incumbent home= inert seam.
"""
from __future__ import annotations

import hashlib
import json
import os
import pwd
import types
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROLL = Path(__file__).resolve().parent
CAND = ROLL.parent / "candidate"
SRC = ROLL.parent / "source"

RUN_ID = "inert-plain-review-20261020-r1"
ROOT = "inert-root-20261020"
PARENT = "inert-root-20261020"
HOST = "inert-host"
ALIAS = "inert-alias"
MODEL = "glm-5.3"
PACKET = b"REVIEW PACKET: inert plain review request body\n"
STDOUT = b"plain review answer\n"
POLICY = "b" * 64


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def exclusive(path, data, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        assert os.write(fd, data) == len(data)
        os.fsync(fd)
    finally:
        os.close(fd)


class Fixture:
    """One inert controller install plus its account-home and destination."""

    def __init__(self, stack, *, mode='glm', model=MODEL, acquisition_pool='glm-frontier'):
        self.mode, self.model, self.acquisition_pool = mode, model, acquisition_pool
        self.home = Path(tempfile.mkdtemp(prefix="plain-home-", dir=str(stack)))
        self.ctl = Path(tempfile.mkdtemp(prefix="plain-ctl-", dir=str(stack)))
        self.dest_root = self.home / "evidence"
        (self.dest_root / "runs").mkdir(parents=True, mode=0o700)
        # The reviewed install: candidate overlay over the pinned source files.
        for origin, names in ((CAND, ("remote_sub_helpers.py",
                                      "original_delivery_collector.py",
                                      "artifact_delivery.py")),
                              (SRC, ("artifact_reader.py",
                                     "artifact_production.py"))):
            for name in names:
                shutil.copyfile(origin / name, self.ctl / name)
        exclusive(self.ctl / "native_runtime_bindings.py",
                  b"from pathlib import Path\n"
                  b"def owner_path(path, here=None):\n"
                  b"    value = Path(path)\n"
                  b"    return value if value.is_absolute() else Path(here) / value\n")
        exclusive(self.ctl / "hosts.json", json.dumps(
            {HOST: {"allowed_modes": [self.mode], "ssh_alias": ALIAS}}).encode())
        (self.ctl / "state" / "remote_sub").mkdir(parents=True, mode=0o700)
        for name in ("lanes/tmp", "lanes/ext/lanes",
                     "lanes/support-releases"):
            (self.home / name).mkdir(parents=True, mode=0o700)
        self.packet = PACKET
        self.stdout = STDOUT
        self.support_manifest = {
            "artifact_production.py": sha((self.ctl / "artifact_production.py").read_bytes()),
            "artifact_reader.py": sha((self.ctl / "artifact_reader.py").read_bytes())}
        self.support_digest = sha(json.dumps(
            {"schema": "remote-support-code.v1", "files": self.support_manifest},
            sort_keys=True, separators=(",", ":")).encode())
        # Remote (account home) evidence, as a settled plain run leaves it.
        exclusive(self.home / f"lanes/tmp/{RUN_ID}.txt", self.packet)
        exclusive(self.home / f"lanes/ext/lanes_{RUN_ID}.rc", b"0\n")
        exclusive(self.home / f"lanes/ext/lanes_{RUN_ID}.stdout", self.stdout)
        exclusive(self.home / f"lanes/ext/lanes/{RUN_ID}.process.jsonl", json.dumps({
            "schema": "mastermind.local_owned_process_receipt.v1", "label": RUN_ID,
            "returncode": 0, "timed_out": False, "pid": 4242, "pgid": 4242,
            "stdout_bytes": len(self.stdout), "stderr_bytes": 0,
            "stdout_truncated": False, "stderr_truncated": False,
            "started_at": "2026-10-20T00:00:00Z", "ended_at": "2026-10-20T00:01:00Z",
            "runtime_failure_code": None, "stdout_sha256": sha(self.stdout),
            "cleanup": {"identity_verified": True, "census_proven": True,
                        "residual_count": 0, "status": "not_needed", "error_code": None,
                        "stdin_delivery_complete": True, "stdin_delivery_error": None,
                        "stdout_capture_complete": True, "stdout_capture_error": None,
                        "stderr_capture_complete": True, "stderr_capture_error": None}},
            sort_keys=True).encode() + b"\n")
        release = self.home / f"lanes/support-releases/{self.support_digest}"
        (release / "ext").mkdir(parents=True, mode=0o700)
        exclusive(release / "ext" / "remote_sub_exec.py", b"# inert published reader\n")
        # The published generation carries the immutable RELEASE manifest with
        # the exact digests the controller computed before transport.
        for name in ("artifact_production.py", "artifact_reader.py"):
            exclusive(release / "ext" / name, (self.ctl / name).read_bytes())
        exclusive(release / "RELEASE.json", json.dumps(
            {"schema": "remote-support-code.v1", "digest": self.support_digest,
             "files": self.support_manifest},
            sort_keys=True, separators=(",", ":")).encode())
        # Controller-side retained sources, pinned by the binding file. The
        # plain packet uses the controller's retained <run>.request.packet
        # name; artifact runs keep their separate <run>.packet.* naming.
        self.log_path = self.ctl / f"state/remote_sub/{RUN_ID}.log"
        self.packet_pin = self.ctl / f"state/remote_sub/{RUN_ID}.request.packet"
        self.support_pin = self.ctl / f"state/remote_sub/{RUN_ID}.support.json"
        exclusive(self.packet_pin, self.packet)
        exclusive(self.support_pin, json.dumps(
            self.support_manifest, sort_keys=True, separators=(",", ":")).encode())
        self.lease_path = self.ctl / f"state/remote_sub/{RUN_ID}.lease.inert01"
        self.acquire = b"LEASE=0123456789ab ACCOUNT=" + ALIAS.encode() + b"\n"
        exclusive(self.lease_path, self.acquire)
        self.receipt_path = self.ctl / f"state/remote_sub/{RUN_ID}.transport-verified.json"
        self.destination = str(self.dest_root / "runs" / f"{RUN_ID}-collection-v1")
        self.write_binding()

    def binding_path(self):
        return self.ctl / f"state/remote_sub/{RUN_ID}.binding.json"

    def write_binding(self):
        sources = {
            "packet": {"path": str(self.packet_pin), "sha256": sha(self.packet_pin.read_bytes())},
            "log": {"path": str(self.log_path), "sha256": sha(self.log_path.read_bytes())}
            if self.log_path.exists() else {"path": str(self.log_path), "sha256": "0" * 64},
            "support": {"path": str(self.support_pin),
                        "sha256": sha(self.support_pin.read_bytes())}}
        exclusive(self.binding_path(), json.dumps({
            "schema": "mastermind.original_delivery_binding.v1", "run_id": RUN_ID,
            "root": ROOT, "parent": PARENT, "host": HOST, "mode": self.mode,
            "requested_model": self.model, "cwd": "~", "artifact_names": [],
            "sources": sources}, sort_keys=True, separators=(",", ":")).encode())

    def refresh_binding(self):
        self.binding_path().unlink()
        self.write_binding()

    def prelaunch_log(self):
        stamp = "2026-10-20T00:00Z"
        head = f"{stamp} [remote_sub id={RUN_ID} host={HOST}] "
        return "".join(line + "\n" for line in (
            head + "RUN_RESERVED explicit=1",
            head + "LEASE_OK pool=" + self.acquisition_pool,
            head + f"SUPPORT_VERSION_READY digest={self.support_digest} policy={POLICY}"))

    def observation(self, *, packet=None, files=None):
        """The exact bounded JSON the fixed remote readback emits."""
        body = self.packet if packet is None else packet
        return json.dumps({
            "schema": "mastermind.transport_observation.v1", "run_id": RUN_ID,
            "packet_bytes": len(body), "packet_sha256": sha(body),
            "support_digest": self.support_digest, "policy_sha256": POLICY,
            "files": self.support_manifest if files is None else files},
            sort_keys=True, separators=(",", ":")).encode()

    def run_helper(self, args, env=None):
        merge = dict(os.environ)
        merge.update(env or {})
        return subprocess.run(
            [sys.executable, str(self.ctl / "remote_sub_helpers.py"), *args],
            capture_output=True, text=True, timeout=60, env=merge, cwd=str(self.ctl))

    def transport_arguments(self, seen, **overrides):
        values=dict(mode=self.mode, model=self.model, lease_id="0123456789ab",
                    account=ALIAS, acquisition_pool=self.acquisition_pool)
        assert set(overrides) <= set(values)
        values.update(overrides)
        return ["transport-verify", str(self.log_path), str(self.receipt_path),
                str(self.packet_pin), str(self.lease_path), str(seen), RUN_ID, HOST,
                values["mode"], values["model"], self.support_digest, POLICY,
                values["lease_id"], values["account"], values["acquisition_pool"]]

    def launch_arguments(self, **overrides):
        values=dict(mode=self.mode, model=self.model, lease_id="0123456789ab",
                    account=ALIAS, acquisition_pool=self.acquisition_pool)
        assert set(overrides) <= set(values)
        values.update(overrides)
        return ["launch-binding", str(self.log_path), str(self.packet_pin),
                str(self.lease_path), RUN_ID, ROOT, PARENT, HOST,
                values["mode"], values["model"], self.support_digest,
                values["lease_id"], values["account"], str(self.receipt_path),
                values["acquisition_pool"]]

    def verify_transport(self, *, observation=None):
        """Run the real transport verification end-to-end (receipt + log line)."""
        if not self.log_path.exists():
            exclusive(self.log_path, self.prelaunch_log().encode(), 0o600)
        observed = self.observation() if observation is None else observation
        seen = self.ctl / f"state/remote_sub/{RUN_ID}.observation.json"
        if seen.exists():
            seen.unlink()
        exclusive(seen, observed)
        result = self.run_helper(self.transport_arguments(seen))
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(self.receipt_path.read_text())

    def retain_binding(self, env=None):
        """Run the real controller helpers end-to-end and return the binding row."""
        receipt = self.verify_transport()
        result = self.run_helper(self.launch_arguments(), env=env)
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)

    def ssh_shim(self, bin_dir, *, fail=False, mode="reader"):
        """Local ssh carrier shim: runs the generated reader verbatim."""
        shim = bin_dir / "ssh"
        exclusive(shim, b"", 0o700)
        script = f"""#!/usr/bin/env python3
import os, shlex, subprocess, sys
command = shlex.split(sys.argv[-1])
assert command[:4] == ["python3", "-I", "-S", "-c"], command
mode = os.environ.get("INERT_SSH_MODE", "reader")
if mode == "fail":
    sys.exit(9)
if mode == "dropped-reply":
    code = command[4]
    wrapper = ("import pwd, os, types\\n"
               "pwd.getpwuid = lambda uid: types.SimpleNamespace("
               "pw_dir=os.environ['INERT_HOME'])\\n"
               "exec(compile(" + repr(code) + ", 'generated-reader', 'exec'))\\n")
    subprocess.run([sys.executable, "-I", "-S", "-c", wrapper], check=True)
    sys.exit(9)
code = command[4]
wrapper = ("import pwd, os, types\\n"
           "pwd.getpwuid = lambda uid: types.SimpleNamespace("
           "pw_dir=os.environ['INERT_HOME'])\\n"
           "exec(compile(" + repr(code) + ", 'generated-reader', 'exec'))\\n")
sys.exit(subprocess.run([sys.executable, "-I", "-S", "-c", wrapper]).returncode)
"""
        shim.write_text(script)
        os.chmod(shim, 0o700)

    def environment(self, bin_dir):
        env = dict(os.environ)
        env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH','')}"
        env["INERT_HOME"] = str(self.home)
        env["CODEX_THREAD_ID"] = ROOT
        env["POOL_ORCHESTRATOR_ID"] = ROOT
        return env

    def collector_module(self):
        import importlib
        sys.path.insert(0, str(self.ctl))
        for name in ("artifact_reader", "artifact_production", "native_runtime_bindings",
                     "artifact_delivery", "remote_sub_helpers", "original_delivery_collector"):
            if name in sys.modules:
                del sys.modules[name]
        module = importlib.import_module("original_delivery_collector")
        module.delivery.DESTINATION_ROOT = self.dest_root
        return module


def stack(prefix):
    # DirectoryChain deliberately rejects group/world-writable /tmp ancestry;
    # fixture roots live under the account home (or NATIVE_ROLLOUT_TEST_ROOT).
    base = os.environ.get("NATIVE_ROLLOUT_TEST_ROOT", str(Path.home()))
    return tempfile.TemporaryDirectory(prefix=prefix, dir=base)


class AcquisitionProducerCase(unittest.TestCase):
    """Actual producer helpers, with independent acquisition/log identities."""

    def setUp(self):
        self._stack = stack("acquisition-proof-")
        self.addCleanup(self._stack.cleanup)

    def fixture(self, **kwargs):
        return Fixture(Path(self._stack.name), **kwargs)

    def transport_args(self, fx, **overrides):
        exclusive(fx.log_path, fx.prelaunch_log().encode())
        seen = fx.ctl / f"state/remote_sub/{RUN_ID}.observation.json"
        exclusive(seen, fx.observation())
        return fx.transport_arguments(seen, **overrides)

    def test_v2_producers_preserve_all_selected_pool_controls(self):
        for mode, model, pool in (
                ("glm", "glm-5.3", "glm-frontier"),
                ("glm", "glm-5.3", "glm"),
                ("glm", "glm-5.3-flash", "glm"),
                ("qwen", "qwen3.8-flash", "bailian")):
            with self.subTest(mode=mode, model=model, pool=pool):
                fx = self.fixture(mode=mode, model=model, acquisition_pool=pool)
                result = fx.retain_binding()
                self.assertEqual(result["state"], "RETAINED_PRE_LAUNCH")
                receipt = json.loads(fx.receipt_path.read_text())
                line = next(line for line in fx.log_path.read_text().splitlines()
                            if "LAUNCH_BINDING " in line)
                binding = json.loads(line.split("LAUNCH_BINDING ", 1)[1])
                self.assertEqual(receipt["schema"], "mastermind.transport_verification.v2")
                self.assertEqual(binding["schema"], "mastermind.fabric_plain_launch_binding.v2")
                self.assertEqual(binding["pool"], "glm" if mode == "glm" else "bailian")
                self.assertEqual((receipt["acquisition_pool"], binding["acquisition_pool"],
                                  binding["transport"]["acquisition_pool"]), (pool, pool, pool))
                self.assertEqual(binding["acquire_response_sha256"], sha(fx.acquire))
                self.assertIn("LEASE_OK pool=" + pool + "\n", fx.log_path.read_text())

    def test_artifact_producer_emits_selected_tag_without_plain_receipt(self):
        for pool in ("glm-frontier", "glm"):
            with self.subTest(acquisition_pool=pool):
                fx = self.fixture(acquisition_pool=pool)
                production = fx.collector_module().production
                packet = production.encode_packet(
                    "Inert artifact producer acquisition fixture.",
                    root=ROOT, parent=PARENT, run_id=RUN_ID,
                    names=["proof.txt"], support_digest=fx.support_digest).encode()
                fx.packet_pin.write_bytes(packet)
                exclusive(fx.log_path, fx.prelaunch_log().encode())
                args = fx.launch_arguments()
                args[-2] = "-"
                result = fx.run_helper(args)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(json.loads(result.stdout)["state"], "RETAINED_PRE_LAUNCH")
                rows = [line.split("LAUNCH_BINDING ", 1)[1]
                        for line in fx.log_path.read_text().splitlines()
                        if "LAUNCH_BINDING " in line]
                self.assertEqual(len(rows), 1)
                binding = json.loads(rows[0])
                self.assertEqual(binding["schema"], "mastermind.fabric_launch_binding.v2")
                self.assertEqual((binding["pool"], binding["acquisition_pool"]),
                                 ("glm", pool))
                self.assertEqual(binding["packet_sha256"], sha(packet))
                self.assertEqual(binding["support_digest"], fx.support_digest)
                self.assertEqual(binding["acquire_response_sha256"], sha(fx.acquire))
                self.assertNotIn("transport", binding)
                self.assertFalse(fx.receipt_path.exists())

    def test_transport_rejects_wrong_tuple_log_lease_or_account(self):
        control = self.fixture()
        self.assertEqual(control.run_helper(self.transport_args(control)).returncode, 0)
        cases = [
            ({"mode": "qwen"}, "acquisition_pool_scope"),
            ({"model": "glm-5.3-flash"}, "acquisition_pool_scope"),
            ({"acquisition_pool": "glm"}, "transport_verification_log_not_prelaunch"),
            ({"acquisition_pool": "bailian"}, "acquisition_pool_scope"),
            ({"acquisition_pool": "unknown"}, "acquisition_pool_scope"),
            ({"lease_id": "abcdefabcdef"}, "transport_verification_acquire_mismatch"),
            ({"account": "other-account"}, "transport_verification_acquire_mismatch"),
        ]
        for changed, reason in cases:
            with self.subTest(changed=changed):
                fx = self.fixture()
                result = fx.run_helper(self.transport_args(fx, **changed))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(reason, result.stderr)
                self.assertFalse(fx.receipt_path.exists())
                self.assertNotIn("TRANSPORT_VERIFIED", fx.log_path.read_text())

    def test_launch_rejects_wrong_tuple_receipt_lease_or_account(self):
        self.assertEqual(self.fixture().retain_binding()["state"], "RETAINED_PRE_LAUNCH")
        cases = [
            ({"mode": "qwen"}, "acquisition_pool_scope"),
            ({"model": "glm-5.3-flash"}, "acquisition_pool_scope"),
            ({"acquisition_pool": "glm"}, "launch_binding_transport_unconfirmed"),
            ({"acquisition_pool": "bailian"}, "acquisition_pool_scope"),
            ({"acquisition_pool": "unknown"}, "acquisition_pool_scope"),
            ({"lease_id": "abcdefabcdef"}, "launch_binding_launch_mismatch"),
            ({"account": "other-account"}, "launch_binding_launch_mismatch"),
        ]
        for changed, reason in cases:
            with self.subTest(changed=changed):
                fx = self.fixture()
                fx.verify_transport()
                result = fx.run_helper(fx.launch_arguments(**changed))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(reason, result.stderr)
                self.assertNotIn("LAUNCH_BINDING", fx.log_path.read_text())

    def test_launch_rejects_changed_receipt_tag_and_missing_cli_tag(self):
        self.assertEqual(self.fixture().retain_binding()["state"], "RETAINED_PRE_LAUNCH")
        fx = self.fixture()
        receipt = fx.verify_transport()
        receipt["acquisition_pool"] = "glm"
        fx.receipt_path.write_text(json.dumps(receipt))
        result = fx.run_helper(fx.launch_arguments())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("launch_binding_transport_unconfirmed", result.stderr)
        self.assertNotIn("LAUNCH_BINDING", fx.log_path.read_text())
        other = self.fixture()
        args = self.transport_args(other)
        result = other.run_helper(args[:-1])
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(other.receipt_path.exists())
        self.assertNotIn("TRANSPORT_VERIFIED", other.log_path.read_text())


class PlainRepairCase(unittest.TestCase):
    def setUp(self):
        self._stack = stack("plain-repair-proof-")
        self.fx = Fixture(Path(self._stack.name))
        self.bin = Path(self._stack.name) / "bin"
        self.bin.mkdir(mode=0o700)
        self.fx.ssh_shim(self.bin)
        self.env = self.fx.environment(self.bin)
        self.collector = self.fx.collector_module()
        self._saved = {k: os.environ.get(k) for k in
                       ("CODEX_THREAD_ID", "POOL_ORCHESTRATOR_ID", "PATH",
                        "INERT_SSH_MODE", "INERT_HOME")}
        os.environ["CODEX_THREAD_ID"] = ROOT
        os.environ["POOL_ORCHESTRATOR_ID"] = ROOT
        os.environ["INERT_HOME"] = str(self.fx.home)
        # The local ssh shim stands in for the transport carrier only.
        os.environ["PATH"] = f"{self.bin}{os.pathsep}{os.environ.get('PATH','')}"

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        os.environ.pop("INERT_SSH_MODE", None)
        self._stack.cleanup()

    def post_launch(self):
        """Append the exact launch evidence the shell logs after retention."""
        stamp = "2026-10-20T00:01Z"
        head = f"{stamp} [remote_sub id={RUN_ID} host={HOST}] "
        raw = self.fx.log_path.read_bytes()
        self.fx.log_path.unlink()
        exclusive(self.fx.log_path, raw + (
            head + f"LAUNCH stdout=lanes_{RUN_ID}.stdout "
                   f"rc_file=ext/lanes_{RUN_ID}.rc cwd=~\n" +
            head + "LAUNCH_ATTEMPT attempt=1\n").encode())

    def qualified(self):
        """A genuinely qualified new fixture: real retained prelaunch binding."""
        row = self.fx.retain_binding()
        self.assertEqual(row["state"], "RETAINED_PRE_LAUNCH")
        self.post_launch()
        self.fx.refresh_binding()
        return row

    def collect(self):
        return self.collector.collect(self.fx.binding_path(), run_id=RUN_ID,
                                      root=ROOT, parent=PARENT,
                                      destination=self.fx.destination)

    def receipt_on_disk(self):
        raw = (Path(self.fx.destination) / "receipt.json").read_bytes()
        return raw, self.collector.read_collection(
            str(Path(self.fx.destination) / "receipt.json"),
            expected_sha256=sha(raw), run_id=RUN_ID, root=ROOT, parent=PARENT)

    # ---- forward-only positive path ------------------------------------

    def test_qualified_plain_run_collects_and_reads_back_end_to_end(self):
        row = self.qualified()
        receipt = self.collect()
        self.assertEqual(receipt["state"], "COMPLETE")
        self.assertTrue(receipt["delivery_verified"])
        self.assertTrue(receipt["worker_terminal_proof"])
        self.assertEqual(receipt["lease_settlement"], "UNKNOWN")
        self.assertEqual(receipt["controller_state"], "UNKNOWN")
        self.assertEqual(receipt["acceptance"], "NOT_RECORDED")
        self.assertFalse(receipt["original_operation_mutated"])
        binding = receipt["plain_launch_binding"]
        self.assertEqual(binding["schema"], "mastermind.fabric_plain_launch_binding.v2")
        self.assertEqual(binding["pool"], "glm")
        self.assertEqual(binding["acquisition_pool"], self.fx.acquisition_pool)
        self.assertEqual(binding["transport"]["acquisition_pool"], self.fx.acquisition_pool)
        self.assertEqual(binding["phase"], "PRE_LAUNCH")
        self.assertEqual(binding["packet_sha256"], sha(PACKET))
        self.assertEqual(binding["support_digest"], self.fx.support_digest)
        self.assertEqual(binding["acquire_response_sha256"], sha(self.fx.acquire))
        self.assertEqual(binding["binding_sha256"], row["binding_sha256"])
        transport = binding["transport"]
        self.assertEqual(transport["packet_sha256"], sha(PACKET))
        self.assertEqual(transport["support_digest"], self.fx.support_digest)
        self.assertEqual(transport["policy_sha256"], POLICY)
        self.assertEqual(transport["files"], self.fx.support_manifest)
        self.assertEqual(transport["lease_id"], "0123456789ab")
        self.assertEqual(transport["account"], ALIAS)
        self.assertEqual(transport["phase"], "PRE_LAUNCH")
        self.assertRegex(transport["verified_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z$")
        raw, stdout = self.receipt_on_disk()
        self.assertEqual(stdout, STDOUT)
        self.assertEqual(sha(stdout), receipt["stdout_sha256"])
        names = [item["local_name"] for item in receipt["files"]]
        self.assertEqual(names, ["binding.json", "stdout.000", "process.json",
                                 "returncode.txt"])
        self.assertEqual(receipt["artifacts"], [])
        self.assertIsNone(receipt.get("artifact_manifest"))

    def rewrite_retained_binding(self, transform, *, ordinary_log=False):
        log = self.fx.log_path.read_text()
        marker = "LAUNCH_BINDING "
        line = next(line for line in log.splitlines() if marker in line)
        record = json.loads(line.split(marker, 1)[1])
        transform(record)
        changed = line.split(marker, 1)[0] + marker + json.dumps(
            record, sort_keys=True, separators=(",", ":"))
        log = log.replace(line, changed)
        if ordinary_log:
            log = log.replace("LEASE_OK pool=glm-frontier\n", "LEASE_OK pool=glm\n")
        self.fx.log_path.write_text(log)
        self.fx.refresh_binding()

    def test_original_v1_plain_record_still_collects_under_its_original_rule(self):
        self.qualified()
        def legacy(record):
            record["schema"] = "mastermind.fabric_plain_launch_binding.v1"
            record.pop("acquisition_pool")
            record["transport"].pop("acquisition_pool")
        self.rewrite_retained_binding(legacy, ordinary_log=True)
        receipt = self.collect()
        self.assertEqual(receipt["plain_launch_binding"]["schema"],
                         "mastermind.fabric_plain_launch_binding.v1")
        self.assertEqual(self.receipt_on_disk()[1], STDOUT)
        self.assertEqual(receipt["lease_settlement"], "UNKNOWN")
        self.assertEqual(receipt["acceptance"], "NOT_RECORDED")

    def test_v1_does_not_gain_frontier_qualification(self):
        self.qualified()
        def legacy(record):
            record["schema"] = "mastermind.fabric_plain_launch_binding.v1"
            record.pop("acquisition_pool")
            record["transport"].pop("acquisition_pool")
        self.rewrite_retained_binding(legacy)
        with self.assertRaisesRegex(ValueError, "plain_launch_binding_event_sequence_invalid"):
            self.collect()

    def test_collector_rejects_v2_missing_unknown_or_inconsistent_tags(self):
        self.qualified()
        self.collector.load_binding(self.fx.binding_path(), run_id=RUN_ID,
                                    root=ROOT, parent=PARENT)
        original = self.fx.log_path.read_text()
        mutations = (
            lambda r: r.pop("acquisition_pool"),
            lambda r: r["transport"].pop("acquisition_pool"),
            lambda r: r["transport"].update(acquisition_pool="glm"),
            lambda r: r.update(schema="mastermind.fabric_plain_launch_binding.v99"),
            lambda r: r.update(schema="mastermind.fabric_plain_launch_binding.v1"),
            lambda r: (r.update(acquisition_pool="glm"),
                       r["transport"].update(acquisition_pool="glm")),
        )
        for number, mutate in enumerate(mutations):
            with self.subTest(number=number):
                self.fx.log_path.write_text(original)
                self.rewrite_retained_binding(mutate)
                with self.assertRaises(ValueError):
                    self.collect()
                self.assertFalse(Path(self.fx.destination).exists())

    def test_retained_binding_requires_confirmed_prelaunch_transport(self):
        # Missing SUPPORT_VERSION_READY readback: the real helper refuses to
        # append anything, so no future collection can qualify this run.
        log = self.fx.prelaunch_log().splitlines(True)
        log = [line for line in log if "SUPPORT_VERSION_READY" not in line]
        exclusive(self.fx.log_path, "".join(log).encode())
        self.fx.refresh_binding()
        result = self.fx.run_helper(
            ["transport-verify", str(self.fx.log_path), str(self.fx.receipt_path),
             str(self.fx.packet_pin), str(self.fx.lease_path),
             str(self.fx.ctl / f"state/remote_sub/{RUN_ID}.observation.json"),
             RUN_ID, HOST, "glm", MODEL, self.fx.support_digest, POLICY,
             "0123456789ab", ALIAS, self.fx.acquisition_pool])
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("TRANSPORT_VERIFIED", self.fx.log_path.read_text())
        with self.assertRaises(ValueError) as caught:
            self.collect()
        self.assertIn("original_producer_contract_unavailable", str(caught.exception))

    def test_faked_support_version_ready_without_packet_verification_refuses(self):
        # The bug this repair closes: a log that merely claims support
        # publication never proves the transported packet bytes. With no
        # actual transport receipt, the real launch binding refuses to append
        # anything and the collector can never qualify the run.
        exclusive(self.fx.log_path, self.fx.prelaunch_log().encode())
        self.fx.refresh_binding()
        result = self.fx.run_helper(
            ["launch-binding", str(self.fx.log_path), str(self.fx.packet_pin),
             str(self.fx.lease_path), RUN_ID, ROOT, PARENT, HOST, "glm", MODEL,
             self.fx.support_digest, "0123456789ab", ALIAS, "-", self.fx.acquisition_pool])
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("LAUNCH_BINDING", self.fx.log_path.read_text())
        with self.assertRaises(ValueError) as caught:
            self.collect()
        self.assertIn("original_producer_contract_unavailable", str(caught.exception))

    def test_mutated_remote_packet_before_prelaunch_refuses(self):
        # The remote readback reports different packet bytes than the local
        # retained original: transport verification fails, no TRANSPORT_VERIFIED
        # line is ever appended, and the launch binding refuses.
        exclusive(self.fx.log_path, self.fx.prelaunch_log().encode())
        self.fx.refresh_binding()
        seen = self.fx.ctl / f"state/remote_sub/{RUN_ID}.observation.json"
        exclusive(seen, self.fx.observation(packet=PACKET + b"tampered\n"))
        result = self.fx.run_helper(
            ["transport-verify", str(self.fx.log_path), str(self.fx.receipt_path),
             str(self.fx.packet_pin), str(self.fx.lease_path), str(seen), RUN_ID,
             HOST, "glm", MODEL, self.fx.support_digest, POLICY,
             "0123456789ab", ALIAS, self.fx.acquisition_pool])
        self.assertNotEqual(result.returncode, 0)
        log = self.fx.log_path.read_text()
        self.assertNotIn("TRANSPORT_VERIFIED", log)
        self.assertNotIn("LAUNCH_BINDING", log)
        self.assertFalse(self.fx.receipt_path.exists())

    def test_support_release_manifest_mismatch_refuses(self):
        # A published code file that does not hash to its manifest entry (or a
        # manifest whose canonical digest is not the computed generation) is a
        # failed transport readback: refuse before any binding.
        exclusive(self.fx.log_path, self.fx.prelaunch_log().encode())
        self.fx.refresh_binding()
        seen = self.fx.ctl / f"state/remote_sub/{RUN_ID}.observation.json"
        exclusive(seen, self.fx.observation(
            files=dict(self.fx.support_manifest,
                       **{"artifact_reader.py": "c" * 64})))
        result = self.fx.run_helper(
            ["transport-verify", str(self.fx.log_path), str(self.fx.receipt_path),
             str(self.fx.packet_pin), str(self.fx.lease_path), str(seen), RUN_ID,
             HOST, "glm", MODEL, self.fx.support_digest, POLICY,
             "0123456789ab", ALIAS, self.fx.acquisition_pool])
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("TRANSPORT_VERIFIED", self.fx.log_path.read_text())

    def test_wrong_root_or_parent_refuses(self):
        self.qualified()
        for field, wrong in (("root", "inert-root-9999"), ("parent", "inert-root-9999")):
            args = {"run_id": RUN_ID, "root": ROOT, "parent": PARENT}
            args[field] = wrong
            with self.assertRaises(ValueError):
                self.collector.collect(self.fx.binding_path(), run_id=args["run_id"],
                                       root=args["root"], parent=args["parent"],
                                       destination=self.fx.destination)
        self.assertFalse((Path(self.fx.destination) / "receipt.json").exists())

    def test_wrong_host_refuses(self):
        self.qualified()
        path = self.fx.binding_path()
        raw = json.loads(path.read_text())
        path.unlink()
        raw["host"] = "other-host"
        exclusive(path, json.dumps(raw, sort_keys=True,
                   separators=(",", ":")).encode())
        with self.assertRaises(ValueError) as caught:
            self.collect()
        # The foreign host never even matches the retained producer log.
        self.assertIn("original_log_scope_mismatch", str(caught.exception))

    def test_changed_packet_bytes_refuse(self):
        self.qualified()
        self.fx.packet_pin.unlink()
        exclusive(self.fx.packet_pin, PACKET + b"tampered\n")
        self.fx.refresh_binding()
        with self.assertRaises(ValueError) as caught:
            self.collect()
        self.assertIn("plain_launch_binding_packet_mismatch", str(caught.exception))

    def test_changed_support_generation_refuses(self):
        self.qualified()
        # Keep the log's retained digest, swap the actual support generation.
        changed = dict(self.fx.support_manifest)
        changed["artifact_reader.py"] = "c" * 64
        self.fx.support_pin.unlink()
        exclusive(self.fx.support_pin, json.dumps(changed, sort_keys=True,
                   separators=(",", ":")).encode())
        self.fx.refresh_binding()
        with self.assertRaises(ValueError) as caught:
            self.collect()
        # Fail closed: either the retained digest or the exact code-group
        # validator refuses the swapped generation.
        self.assertTrue(any(reason in str(caught.exception) for reason in
                            ("original_support_mismatch",
                             "original_producer_validator_changed")),
                        str(caught.exception))

    def test_missing_or_duplicated_record_refuses(self):
        # Missing: the pre-repair controller appended nothing.
        exclusive(self.fx.log_path, self.fx.prelaunch_log().encode())
        self.fx.refresh_binding()
        with self.assertRaises(ValueError) as caught:
            self.collect()
        self.assertIn("original_producer_contract_unavailable", str(caught.exception))
        # Duplicated: two retained records never qualify one run.
        self.qualified()
        raw = self.fx.log_path.read_bytes()
        binding_line = [line for line in raw.splitlines(True)
                        if b"LAUNCH_BINDING" in line][0]
        self.fx.log_path.unlink()
        exclusive(self.fx.log_path, raw + binding_line)
        self.fx.refresh_binding()
        with self.assertRaises(ValueError) as caught:
            self.collect()
        self.assertIn("plain_launch_binding_event_sequence_invalid",
                      str(caught.exception))

    def test_unknown_record_fields_refuse(self):
        self.qualified()
        log = self.fx.log_path.read_text()
        marker = "LAUNCH_BINDING "
        line = next(l for l in log.splitlines() if marker in l)
        row = json.loads(line.split(marker, 1)[1])
        row["operator_note"] = "extra"
        forged = line.split(marker, 1)[0] + marker + json.dumps(
            row, sort_keys=True, separators=(",", ":")) + "\n"
        self.fx.log_path.unlink()
        exclusive(self.fx.log_path, forged.encode())
        self.fx.refresh_binding()
        with self.assertRaises(ValueError) as caught:
            self.collect()
        self.assertIn("plain_launch_binding_invalid", str(caught.exception))

    def test_unknown_transport_receipt_fields_refuse(self):
        self.qualified()
        log = self.fx.log_path.read_text()
        marker = "LAUNCH_BINDING "
        line = next(l for l in log.splitlines() if marker in l)
        row = json.loads(line.split(marker, 1)[1])
        row["transport"]["operator_note"] = "extra"
        forged = line.split(marker, 1)[0] + marker + json.dumps(
            row, sort_keys=True, separators=(",", ":")) + "\n"
        self.fx.log_path.unlink()
        exclusive(self.fx.log_path, forged.encode())
        self.fx.refresh_binding()
        with self.assertRaises(ValueError) as caught:
            self.collect()
        self.assertIn("plain_launch_binding_invalid", str(caught.exception))

    def test_collector_rejects_moved_binding_after_launch(self):
        self.qualified()
        lines = self.fx.log_path.read_text().splitlines(True)
        binding = next(l for l in lines if "LAUNCH_BINDING " in l)
        moved = [l for l in lines if "LAUNCH_BINDING " not in l]
        moved.append(binding)  # record moved after the launch events
        self.fx.log_path.unlink()
        exclusive(self.fx.log_path, "".join(moved).encode())
        self.fx.refresh_binding()
        with self.assertRaises(ValueError) as caught:
            self.collect()
        self.assertIn("plain_launch_binding_event_sequence_invalid",
                      str(caught.exception))

    def test_collector_rejects_altered_transport_line(self):
        self.qualified()
        log = self.fx.log_path.read_text()
        line = next(l for l in log.splitlines()
                    if " TRANSPORT_VERIFIED " in l)
        forged_line = line.rstrip("\n")[:-1] + ("0" if line.rstrip("\n")[-1] != "0"
                                                else "1") + "\n"
        self.fx.log_path.unlink()
        exclusive(self.fx.log_path, log.replace(line, forged_line).encode())
        self.fx.refresh_binding()
        with self.assertRaises(ValueError) as caught:
            self.collect()
        self.assertIn("plain_launch_binding_event_sequence_invalid",
                      str(caught.exception))

    def test_collector_rejects_forbidden_and_crash_cut_logs(self):
        def fresh_qualified():
            self.fx.log_path.unlink(missing_ok=True)
            self.fx.receipt_path.unlink(missing_ok=True)
            self.qualified()
            return self.fx.log_path.read_text().splitlines(True)
        # (a) crash cut before the acquire: no LEASE_OK, no later evidence.
        raw = fresh_qualified()
        def rewrite(lines):
            self.fx.log_path.unlink()
            exclusive(self.fx.log_path, "".join(lines).encode())
            self.fx.refresh_binding()
        rewrite([l for l in raw if "LAUNCH" not in l and "LEASE_OK" not in l
                 and "SUPPORT_VERSION_READY" not in l and "TRANSPORT_VERIFIED" not in l])
        with self.assertRaises(ValueError) as caught:
            self.collect()
        self.assertIn("original_producer_contract_unavailable", str(caught.exception))
        # (b) crash cut after acquire, before confirmed transfer.
        raw = fresh_qualified()
        rewrite([l for l in raw if "SUPPORT_VERSION_READY" not in l
                 and "TRANSPORT_VERIFIED" not in l
                 and "LAUNCH_BINDING" not in l
                 and "LAUNCH " not in l and "LAUNCH_ATTEMPT" not in l])
        with self.assertRaises(ValueError) as caught:
            self.collect()
        self.assertIn("original_producer_contract_unavailable", str(caught.exception))
        # (c) crash cut after confirmed transfer, before the fsynced binding:
        # the evidence sequence is broken and can never qualify the run.
        raw = fresh_qualified()
        rewrite([l for l in raw if "LAUNCH_BINDING" not in l])
        with self.assertRaises(ValueError) as caught:
            self.collect()
        self.assertIn("plain_launch_binding_event_sequence_invalid",
                      str(caught.exception))
        # (d) an actual refusal before launch cannot qualify a run.
        raw = fresh_qualified()
        launch = next(i for i,line in enumerate(raw) if '] LAUNCH ' in line)
        rewrite(raw[:launch] + [f"2026-10-20T09:00Z [remote_sub id={RUN_ID} host={HOST}] "
                               "TRANSPORT_READBACK_REFUSED rc=78\n"] + raw[launch:])
        with self.assertRaises(ValueError) as caught:
            self.collect()
        self.assertIn("plain_launch_binding_forbidden_event", str(caught.exception))

    def test_native_handle_loss_delivers_bytes_without_settling_lifecycle(self):
        self.qualified()
        with self.fx.log_path.open('a') as log:
            log.write(f"2026-10-20T09:00Z [remote_sub id={RUN_ID} host={HOST}] "
                      "LEASE_PRESERVED effect_unknown=1 lease=0123456789ab\n")
        self.fx.refresh_binding()
        receipt = self.collect()
        self.assertEqual(receipt['state'], 'COMPLETE')
        self.assertEqual(receipt['lease_settlement'], 'UNKNOWN')
        self.assertEqual(receipt['controller_state'], 'UNKNOWN')
        self.assertEqual(receipt['acceptance'], 'NOT_RECORDED')
        self.assertFalse(receipt['original_operation_mutated'])
        _, stdout = self.receipt_on_disk()
        self.assertEqual(stdout, STDOUT)

    def transport_reader(self):
        shell = (CAND / 'remote_sub.sh').read_text()
        source = shell.split("<<'PY_VERIFY_PLAIN_TRANSPORT'\n", 1)[1].split(
            '\nPY_VERIFY_PLAIN_TRANSPORT', 1)[0]
        source = source.replace('$PLAIN_TRANSPORT_CHAIN_SOURCE',
                                self.collector.delivery.remote_directory_chain_source())
        # The bound reader receives the publisher's physical lanes root.
        arguments = ["reader", RUN_ID, self.fx.support_digest, POLICY,
                     str(self.fx.home / "lanes")]
        prefix = ('import sys\n'
                  f'sys.argv={arguments!r}\n')
        return subprocess.run([sys.executable, '-I', '-S', '-c', prefix + source],
                              capture_output=True, text=True, timeout=10)

    def test_actual_transport_reader_hashes_original_packet_and_code(self):
        result = self.transport_reader()
        self.assertEqual(result.returncode, 0, result.stderr)
        row = json.loads(result.stdout)
        self.assertEqual(row['packet_sha256'], sha(PACKET))
        self.assertEqual(row['files'], self.fx.support_manifest)

    def test_actual_transport_reader_refuses_symlink_ancestor(self):
        before = self.transport_reader()
        self.assertEqual(before.returncode, 0, before.stderr)
        packet_directory = self.fx.home / 'lanes/tmp'
        packet_directory.rename(self.fx.home / 'lanes/real-tmp')
        packet_directory.symlink_to('real-tmp', target_is_directory=True)
        result = self.transport_reader()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')

    def test_collector_rejects_unreconstructable_acquire_observation(self):
        self.qualified()
        log = self.fx.log_path.read_text()
        marker = "LAUNCH_BINDING "
        line = next(l for l in log.splitlines() if marker in l)
        row = json.loads(line.split(marker, 1)[1])
        # A digest that matches neither reconstruction of the acquired bytes
        # (with or without the trailing newline) can never be validated from a
        # current broker row: refuse.
        row["acquire_response_sha256"] = "d" * 64
        row["transport"]["acquire_response_sha256"] = "d" * 64
        forged = line.split(marker, 1)[0] + marker + json.dumps(
            row, sort_keys=True, separators=(",", ":")) + "\n"
        self.fx.log_path.unlink()
        exclusive(self.fx.log_path, forged.encode())
        self.fx.refresh_binding()
        with self.assertRaises(ValueError) as caught:
            self.collect()
        self.assertIn("plain_launch_binding_acquire_unverified", str(caught.exception))

    def test_truncated_retained_log_refuses(self):
        self.qualified()
        raw = self.fx.log_path.read_bytes()
        self.fx.log_path.unlink()
        exclusive(self.fx.log_path, raw.rstrip(b"\n"))  # crash cut mid-line
        self.fx.refresh_binding()
        with self.assertRaises(ValueError) as caught:
            self.collect()
        self.assertIn("plain_launch_binding_log_truncated", str(caught.exception))

    def test_post_launch_ordering_never_retains(self):
        # A LAUNCH line already present is not a fresh prelaunch log.
        self.fx.verify_transport()
        stamp = "2026-10-20T00:01Z"
        head = f"{stamp} [remote_sub id={RUN_ID} host={HOST}] "
        grown = self.fx.log_path.read_text() + (
            head + f"LAUNCH stdout=lanes_{RUN_ID}.stdout "
                   f"rc_file=ext/lanes_{RUN_ID}.rc cwd=~\n")
        self.fx.log_path.unlink()
        exclusive(self.fx.log_path, grown.encode())
        result = self.fx.run_helper(
            ["launch-binding", str(self.fx.log_path), str(self.fx.packet_pin),
             str(self.fx.lease_path), RUN_ID, ROOT, PARENT, HOST, "glm", MODEL,
             self.fx.support_digest, "0123456789ab", ALIAS, str(self.fx.receipt_path),
             self.fx.acquisition_pool])
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("LAUNCH_BINDING", self.fx.log_path.read_text())

    def test_duplicate_destination_stays_fail_closed(self):
        self.qualified()
        first = self.collect()
        self.assertEqual(first["state"], "COMPLETE")
        with self.assertRaises((ValueError, OSError)):
            self.collect()
        raw = (Path(self.fx.destination) / "receipt.json").read_bytes()
        self.assertEqual(sha(raw), sha(json.dumps(first, sort_keys=True,
            separators=(",", ":")).encode()))

    def test_interrupted_collection_leaves_no_terminal_state(self):
        self.qualified()
        real_transport = self.collector.delivery.transport

        def dropped_reply(alias, request):
            real_transport(alias, request)  # reader ran; reply is lost
            raise ValueError("transport_timeout")

        self.collector.delivery.transport = dropped_reply
        try:
            with self.assertRaises(ValueError):
                self.collect()
        finally:
            self.collector.delivery.transport = real_transport
        receipt = Path(self.fx.destination) / "receipt.json"
        self.assertFalse(receipt.exists())
        failure = json.loads((Path(self.fx.destination) /
                              "transport-failure.json").read_text())
        self.assertEqual(failure["state"], "UNAVAILABLE")
        self.assertFalse(failure["retry_authorized"])
        # The retained evidence files exist; the run stays unqualified.
        self.assertFalse((Path(self.fx.destination) / "returncode.txt").exists())
        self.assertFalse((Path(self.fx.destination) / "process.json").exists())

    def test_pending_remote_read_never_becomes_complete(self):
        self.qualified()
        (self.fx.home / f"lanes/ext/lanes_{RUN_ID}.rc").unlink()
        receipt = self.collect()
        self.assertEqual(receipt["state"], "PENDING")
        self.assertFalse(receipt["delivery_verified"])
        self.assertFalse(receipt["worker_terminal_proof"])
        with self.assertRaises(ValueError) as caught:
            self.receipt_on_disk()
        self.assertIn("collection_not_verified", str(caught.exception))

    def test_transport_failure_refuses_and_disables_retry(self):
        self.qualified()
        os.environ["INERT_SSH_MODE"] = "fail"
        try:
            with self.assertRaises(ValueError):
                self.collect()
        finally:
            os.environ["INERT_SSH_MODE"] = "reader"
        self.assertFalse((Path(self.fx.destination) / "receipt.json").exists())
        failure = json.loads((Path(self.fx.destination) /
                              "transport-failure.json").read_text())
        self.assertEqual(failure["reason"], "transport_unavailable")
        with self.assertRaises((ValueError, OSError)):
            self.collect()

    def test_changed_remote_packet_refuses_with_reason(self):
        self.qualified()
        path = self.fx.home / f"lanes/tmp/{RUN_ID}.txt"
        path.unlink()
        exclusive(path, PACKET + b"tampered\n")
        with self.assertRaises(self.collector.OriginalDeliveryRefused) as caught:
            self.collect()
        self.assertEqual(caught.exception.reason, "read_contract_invalid")

    def test_missing_support_release_refuses(self):
        self.qualified()
        shutil.rmtree(self.fx.home / f"lanes/support-releases/{self.fx.support_digest}")
        with self.assertRaises(self.collector.OriginalDeliveryRefused) as caught:
            self.collect()
        self.assertEqual(caught.exception.reason, "read_contract_invalid")

    def test_changed_retained_log_after_collection_refuses(self):
        self.qualified()
        original_collect = self.collector.collect

        def tamper_after_read(path, **kwargs):
            # Mutate the retained log once the remote read is already done.
            real = self.collector.delivery.transport

            def once(alias, request):
                response = real(alias, request)
                raw = self.fx.log_path.read_bytes()
                self.fx.log_path.unlink()
                tamper = (f"2026-10-20T09:00Z [remote_sub id={RUN_ID} "
                          f"host={HOST}] TAMPER 1\n").encode()
                exclusive(self.fx.log_path, raw + tamper)
                return response

            self.collector.delivery.transport = once
            try:
                return original_collect(path, **kwargs)
            finally:
                self.collector.delivery.transport = real

        self.collector.collect = tamper_after_read
        try:
            with self.assertRaises(ValueError) as caught:
                self.collect()
        finally:
            self.collector.collect = original_collect
        self.assertIn("source_changed", str(caught.exception))
        self.assertFalse((Path(self.fx.destination) / "receipt.json").exists())

    def test_historical_scope_keeps_exact_qualification(self):
        # Historical evidence retains its original logical-pool event exactly.
        self.fx.acquisition_pool = "glm"
        self.fx.retain_binding()
        self.fx.refresh_binding()
        self.collector.PLAIN_SCOPES[RUN_ID] = {
            "root": ROOT, "parent": PARENT, "host": HOST, "mode": "glm",
            "requested_model": MODEL, "packet_path": str(self.fx.packet_pin),
            "packet_sha256": sha(PACKET), "support_digest": self.fx.support_digest,
            "destination": self.fx.destination}
        try:
            # A retained prelaunch binding never qualifies a historical scope.
            with self.assertRaises(ValueError) as caught:
                self.collect()
            self.assertIn("plain_launch_binding_unexpected", str(caught.exception))
            # Without the record, the incumbent historical path still works.
            log = self.fx.log_path.read_text().splitlines(True)
            log = [line for line in log if "LAUNCH_BINDING" not in line]
            stamp = "2026-10-20T00:01Z"
            head = f"{stamp} [remote_sub id={RUN_ID} host={HOST}] "
            log.append(head + f"LAUNCH stdout=lanes_{RUN_ID}.stdout "
                              f"rc_file=ext/lanes_{RUN_ID}.rc cwd=~\n")
            log.append(head + "LAUNCH_ATTEMPT attempt=1\n")
            self.fx.log_path.unlink()
            exclusive(self.fx.log_path, "".join(log).encode())
            self.fx.refresh_binding()
            receipt = self.collect()
            self.assertEqual(receipt["state"], "COMPLETE")
            self.assertIsNone(receipt.get("plain_launch_binding"))
            self.assertEqual(receipt["plain_provenance"]["scope"],
                             "retained_packet_and_process_capture_at_collection")
            raw, stdout = self.receipt_on_disk()
            self.assertEqual(stdout, STDOUT)
        finally:
            self.collector.PLAIN_SCOPES.pop(RUN_ID, None)


class GeneratedReaderCase(unittest.TestCase):
    """The exact generated remote reader against inert directories only."""

    def setUp(self):
        self._stack = stack("plain-generated-")
        self.fx = Fixture(Path(self._stack.name))
        self.binding_row = self.fx.retain_binding()
        self.collector = self.fx.collector_module()
        self.contract = {
            "schema": self.collector.PLAIN_SCHEMA, "run_id": RUN_ID,
            "root": ROOT, "parent": PARENT, "names": [],
            "packet_sha256": sha(PACKET), "support_digest": self.fx.support_digest,
            "binding_sha256": self.binding_row["binding_sha256"],
            "acquire_response_sha256": sha(self.fx.acquire)}
        self.request = {"schema": self.collector.SCHEMA, "run_id": RUN_ID,
                        "root": ROOT, "parent": PARENT, "host": HOST,
                        "contract": self.contract}
        self.namespace = {}
        code = self.collector.code_for_request(self.request)
        # Drop the trailing stdin driver; the reader functions stay verbatim.
        code = code[:code.rfind("\ntry:\n raw=")]
        exec(compile(code, "generated-original-reader", "exec"), self.namespace)
        # Account-home seam only: the remote host's home is the fixture home.
        self._real_getpwuid = pwd.getpwuid
        pwd.getpwuid = lambda uid: types.SimpleNamespace(pw_dir=str(self.fx.home))

    def tearDown(self):
        pwd.getpwuid = self._real_getpwuid
        self._stack.cleanup()

    def test_reads_complete_inert_result_without_scope_injection(self):
        self.assertNotIn(RUN_ID, self.namespace["PLAIN_SCOPES"])
        result = self.namespace["remote_read"](self.request, home=self.fx.home)
        self.assertEqual(result["state"], "READ")
        self.assertEqual(set(result["files"]), {"rc", "process", "stdout"})
        self.assertEqual(result["files"]["rc"]["bytes"], 2)
        import base64
        stdout = base64.b64decode(result["files"]["stdout"]["data_base64"])
        self.assertEqual(stdout, STDOUT)

    def test_pending_when_rc_is_absent(self):
        (self.fx.home / f"lanes/ext/lanes_{RUN_ID}.rc").unlink()
        result = self.namespace["remote_read"](self.request, home=self.fx.home)
        self.assertEqual(result["state"], "PENDING")
        self.assertEqual(result["files"], {})

    def test_scope_and_digest_mismatches_refuse(self):
        wrong_root = dict(self.request, root="inert-root-9999")
        envelope = self.namespace["remote_envelope"](wrong_root)
        self.assertEqual(envelope["reason"], "read_contract_invalid")
        path = self.fx.home / f"lanes/tmp/{RUN_ID}.txt"
        kept = path.read_bytes()
        path.unlink()
        exclusive(path, kept + b"tampered\n")
        envelope = self.namespace["remote_envelope"](self.request)
        self.assertEqual(envelope["reason"], "read_contract_invalid")
        path.unlink()
        exclusive(path, kept)
        shutil.rmtree(self.fx.home / f"lanes/support-releases/{self.fx.support_digest}")
        envelope = self.namespace["remote_envelope"](self.request)
        self.assertEqual(envelope["reason"], "read_contract_invalid")

    def test_full_support_generation_hash_check(self):
        # The reader verifies every published code file hash, not just a
        # nonempty remote_sub_exec file: one swapped byte in any published file
        # refuses the read.
        release = self.fx.home / f"lanes/support-releases/{self.fx.support_digest}"
        target = release / "ext" / "artifact_reader.py"
        kept = target.read_bytes()
        target.unlink()
        exclusive(target, kept + b"\n")
        envelope = self.namespace["remote_envelope"](self.request)
        self.assertEqual(envelope["reason"], "read_contract_invalid")
        target.unlink()
        exclusive(target, kept)
        # A release whose RELEASE.json digest field does not bind the contract
        # generation is equally unqualified.
        raw = json.loads((release / "RELEASE.json").read_text())
        (release / "RELEASE.json").unlink()
        exclusive(release / "RELEASE.json", json.dumps(
            dict(raw, digest="e" * 64), sort_keys=True,
            separators=(",", ":")).encode())
        envelope = self.namespace["remote_envelope"](self.request)
        self.assertEqual(envelope["reason"], "read_contract_invalid")
        (release / "RELEASE.json").unlink()
        exclusive(release / "RELEASE.json", json.dumps(
            raw, sort_keys=True, separators=(",", ":")).encode())
        result = self.namespace["remote_read"](self.request, home=self.fx.home)
        self.assertEqual(result["state"], "READ")

    def test_unbound_plain_contract_is_never_admitted(self):
        legacy_shape = {k: v for k, v in self.contract.items()
                        if k not in ("binding_sha256", "acquire_response_sha256")}
        envelope = self.namespace["remote_envelope"](
            dict(self.request, run_id="inert-unbound-run",
                 root="inert-root-9999", parent="inert-root-9999",
                 contract=legacy_shape))
        self.assertEqual(envelope["reason"], "read_contract_invalid")
        historical_shape = dict(legacy_shape, run_id="inert-unbound-run",
                                root="inert-root-9999", parent="inert-root-9999")
        self.namespace["PLAIN_SCOPES"]["inert-unbound-run"] = {
            "root": "inert-root-9999", "parent": "inert-root-9999",
            "host": HOST, "packet_sha256": sha(PACKET),
            "support_digest": self.fx.support_digest}
        exclusive(self.fx.home / "lanes/tmp/inert-unbound-run.txt", PACKET)
        try:
            envelope = self.namespace["remote_envelope"](
                dict(self.request, run_id="inert-unbound-run",
                     root="inert-root-9999", parent="inert-root-9999",
                     contract=historical_shape))
            self.assertEqual(envelope["state"], "PENDING")
        finally:
            self.namespace["PLAIN_SCOPES"].pop("inert-unbound-run", None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
