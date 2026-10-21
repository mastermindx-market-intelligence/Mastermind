#!/usr/bin/env python3
"""Inert end-to-end proof for collected-source quality attestation and honest
read-only settlement assessment.

Exercises the real read-only collector (original_delivery_collector.py
collect / read_collection / retained_collection_quality), the real ledger
owner overlay (candidate pool_ledger.py publish_collection_quality under the
existing ledger.jsonl.lock: owner-only path inputs, retained descriptors,
fail-closed publication, guarded closed readback) and the additive fabric_task
CLI composition, against inert fixture directories. No SSH, lease, provider,
installed-support or lifecycle effect. Only three carriers are substituted,
all of them test-owned stand-ins for the remote side: the ssh binary (a local
shim that runs the generated reader verbatim against a fixture account home),
the account-home resolution seam (the incumbent home= inert seam), and the
artifact carrier root inside the shim process only (the generated reader's
"/tmp" directory open is redirected to the fixture's private artifacts root,
so production path safety is unchanged and the exact advertised /tmp contract
paths are still what every manifest binds).

The fixture never touches a shared /tmp contract directory: the artifact
bytes live in one private fixture-owned root, created exclusively (a
preexisting destination refuses), and the incumbent
artifact_production.observed_manifest(owner=...) held-directory seam observes
them while preserving the exact advertised paths. The fixture is therefore
portable to hosts where /tmp is a symlink (macOS) without weakening any
production check.

The bundle supplies the whole top-level import dependency closure, so the
inert install copies the REAL deep adapters (pick, a04_terminal_reconcile,
native_prestart_reconcile, native_preexec_reconcile,
native_host_review_controller_reconcile, lane_runtime, model_tier and the
support bundle) rather than stubs; the full CLI runs against them. Those
adapters are imported and loaded for real, but the quality/settlement code
paths under test do not call into them, and no result below claims native
composition for those adapters. The retained LAUNCH_BINDING record, the
artifact producer contract, the strict ledger writer and the broker snapshot
seam are the real bundled owner code, and the retained OLD source
pool_ledger.py is loaded unchanged for the legacy compatibility cases.
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROLL = Path(__file__).resolve().parent
CAND = ROLL.parent / "candidate"
SRC = ROLL.parent / "source"

RUN_ID = "inert-quality-review-20261020-r1"
ROOT = "inert-quality-root-20261020"
PARENT = "inert-quality-parent-20261020"
HOST = "inert-host"
ALIAS = "inert-alias"
MODEL = "glm-5.3"
NAME = "answer.md"
BODY = "QUALITY REVIEW PACKET: inert artifact request body\n"
ANSWER = "inert artifact answer line\n"
POLICY = "b" * 64
LEASE_ID = "0123456789ab"
ADJ_SCHEMA = "mastermind.collection_quality_adjudication.v1"
QUALITY_SCHEMA = "mastermind.collection_quality_attestation.v1"

_OLD_SEQUENCE = []


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def exclusive(path, data, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        assert os.write(fd, data) == len(data)
        os.fsync(fd)
    finally:
        os.close(fd)


def load_old_ledger(path, tag):
    """Execute the retained OLD source/pool_ledger.py under a private name."""
    spec = importlib.util.spec_from_file_location(f"old_pool_ledger_{tag}_{len(_OLD_SEQUENCE)}", path)
    module = importlib.util.spec_from_file_location and importlib.util.module_from_spec(spec)
    _OLD_SEQUENCE.append(tag)
    spec.loader.exec_module(module)
    return module


class ArtifactDirectory:
    """Held inert artifact directory root for the incumbent owner seam.

    Mirrors the production NewDirectory held-descriptor mechanics — one strict
    O_DIRECTORY|O_NOFOLLOW open plus identity re-verification — while keeping
    the actual bytes inside this suite's private fixture root. The advertised
    contract paths are unchanged: observed_manifest still reports the exact
    /tmp/fabric-<hash>/<name> paths and every digest, length and mode check in
    production.read_owned_files runs for real.
    """

    def __init__(self, path, name):
        self.name = name
        self.fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(self.fd)
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("artifact_directory_not_directory")
        self.identity = (info.st_dev, info.st_ino)

    def verify(self):
        info = os.fstat(self.fd)
        if (not stat.S_ISDIR(info.st_mode)
                or (info.st_dev, info.st_ino) != self.identity):
            raise ValueError("artifact_directory_changed")

    def close(self):
        os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class Fixture:
    """One inert controller install, account home, destination and ledger."""

    CANDIDATE_FILES = ("remote_sub_helpers.py", "original_delivery_collector.py",
                       "artifact_delivery.py", "fabric_task.py", "pool_ledger.py",
                       "pick.py", "native_prestart_reconcile.py",
                       "native_preexec_reconcile.py", "support_bundle.py",
                       "remote_sub.sh")
    SOURCE_FILES = ("artifact_reader.py", "artifact_production.py",
                    "native_completion_reconcile.py", "a04_terminal_reconcile.py",
                    "native_host_review_controller_reconcile.py", "lane_runtime.py",
                    "model_tier.py")

    def __init__(self, stack, *, binding_model=MODEL):
        self.binding_model = binding_model
        self.base = Path(stack.name if hasattr(stack, "name") else stack)
        self.home = self.base / "home"
        self.ctl = self.base / "ctl"
        self.dest_root = self.home / "evidence"
        self.ctl.mkdir(mode=0o700)
        (self.dest_root / "runs").mkdir(parents=True, mode=0o700)
        for origin, names in ((CAND, self.CANDIDATE_FILES), (SRC, self.SOURCE_FILES)):
            for name in names:
                shutil.copyfile(origin / name, self.ctl / name)
        exclusive(self.ctl / "native_runtime_bindings.py",
                  b"from pathlib import Path\n"
                  b"def owner_path(path, here=None):\n"
                  b"    value = Path(path)\n"
                  b"    return value if value.is_absolute() else Path(here) / value\n")
        exclusive(self.ctl / "hosts.json", json.dumps(
            {HOST: {"allowed_modes": ["glm"], "ssh_alias": ALIAS}}).encode())
        (self.ctl / "state" / "remote_sub").mkdir(parents=True, mode=0o700)
        for name in ("lanes/tmp", "lanes/ext/lanes", "lanes/support-releases"):
            (self.home / name).mkdir(parents=True, mode=0o700)
        self.ledger_path = self.base / "ledger.jsonl"
        self.adjudication_path = self.base / "adjudication.json"
        self.production, self.delivery, self.collector, self.ledger, self.fabric = \
            self.load_modules()
        self.delivery.DESTINATION_ROOT = self.dest_root
        os.environ["POOL_LEDGER_PATH"] = str(self.ledger_path)
        self.ledger.LEDGER_PATH = str(self.ledger_path)
        self.ledger.LEDGER_DIR = str(self.base)
        self.support_manifest = {
            "artifact_production.py": sha((self.ctl / "artifact_production.py").read_bytes()),
            "artifact_reader.py": sha((self.ctl / "artifact_reader.py").read_bytes())}
        self.support_digest = sha(canonical(
            {"schema": "remote-support-code.v1", "files": self.support_manifest}))
        self.body = BODY.encode()
        # The real producer contract, encoded by the real production owner.
        packet_text = self.production.encode_packet(
            BODY, root=ROOT, parent=PARENT, run_id=RUN_ID, names=[NAME],
            support_digest=self.support_digest)
        self.packet = packet_text.encode()
        self.contract = self.production.parse_packet(packet_text)
        # The artifact bytes live in THIS fixture's private root, created
        # exclusively: a preexisting destination refuses instead of being
        # removed. Only the exact advertised contract path names are reused.
        self.artifact_root = self.base / "fabric-artifacts"
        advertised_directory = Path(self.production.directory(self.contract))
        # The advertised contract directory is external to this fixture and may
        # already exist on a host where an earlier synthetic fixture left it.
        # Its existence and identity are captured without reading any content,
        # and the composed operations assert it unchanged, so the fixture stays
        # portable and never creates, adopts, modifies or removes a preexisting
        # external path (first repair's no-rmtree rule, extended to /tmp).
        self.advertised_directory = advertised_directory
        self.advertised_before = self.advertised_state()
        self.artifact_root.mkdir(mode=0o700)
        self.artifact_dir = self.artifact_root / advertised_directory.name
        self.artifact_dir.mkdir(mode=0o700)
        exclusive(self.artifact_dir / NAME, (ANSWER * 3).encode())
        with self.hold_artifacts() as holder:
            # Incumbent owner seam: exact advertised paths, real byte checks.
            self.manifest = self.production.observed_manifest(self.contract, HOST,
                                                              owner=holder)
        # Worker-side retained evidence in the account home.
        exclusive(self.home / f"lanes/ext/lanes_{RUN_ID}.rc", b"0\n")
        exclusive(self.home / f"lanes/ext/lanes_{RUN_ID}.stdout", self.stdout_text().encode())
        exclusive(self.home / f"lanes/ext/lanes/{RUN_ID}.process.jsonl",
                  self.process_row())
        # Controller-side retained sources, pinned by the binding file.
        self.log_path = self.ctl / f"state/remote_sub/{RUN_ID}.log"
        self.packet_pin = self.ctl / f"state/remote_sub/{RUN_ID}.packet.inert01"
        self.support_pin = self.ctl / f"state/remote_sub/{RUN_ID}.support.json"
        self.lease_path = self.ctl / f"state/remote_sub/{RUN_ID}.lease.inert01"
        exclusive(self.packet_pin, self.packet)
        exclusive(self.support_pin, canonical(self.support_manifest))
        exclusive(self.lease_path, f"LEASE={LEASE_ID} ACCOUNT={ALIAS}\n".encode())
        self.prelaunch_log()
        self.retain_launch_binding()
        self.post_launch_log()
        self.binding_path = self.ctl / f"state/remote_sub/{RUN_ID}.binding.json"
        self.write_binding()
        # The local ssh shim stands in for the transport carrier only.
        self.bin_dir = self.ssh_shim()
        os.environ["CODEX_THREAD_ID"] = ROOT
        os.environ.pop("POOL_ORCHESTRATOR_ID", None)
        os.environ.pop("POOL_PARENT_RUN_ID", None)
        os.environ["INERT_HOME"] = str(self.home)
        os.environ["INERT_ARTIFACT_ROOT"] = str(self.artifact_root)
        os.environ["PATH"] = f"{self.bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"
        self.destination = self.dest_root / "runs" / f"{RUN_ID}-collection-v1"

    # ---- module loading --------------------------------------------------

    def load_modules(self):
        sys.path.insert(0, str(self.ctl))
        for name in ("artifact_reader", "artifact_production", "native_runtime_bindings",
                     "artifact_delivery", "original_delivery_collector",
                     "remote_sub_helpers", "pool_ledger", "fabric_task",
                     "native_completion_reconcile", "model_tier", "pick",
                     "lane_runtime", "a04_terminal_reconcile",
                     "native_prestart_reconcile", "native_preexec_reconcile",
                     "native_host_review_controller_reconcile"):
            sys.modules.pop(name, None)
        production = importlib.import_module("artifact_production")
        delivery = importlib.import_module("artifact_delivery")
        collector = importlib.import_module("original_delivery_collector")
        ledger = importlib.import_module("pool_ledger")
        fabric = importlib.import_module("fabric_task")
        for name in ("native_completion_reconcile", "pick", "a04_terminal_reconcile",
                     "native_prestart_reconcile", "native_preexec_reconcile",
                     "native_host_review_controller_reconcile"):
            importlib.import_module(name)
        return production, delivery, collector, ledger, fabric

    # ---- inert evidence --------------------------------------------------

    def hold_artifacts(self):
        """Held private artifact directory root for the owner seam."""
        return ArtifactDirectory(self.artifact_dir,
                                 self.production.directory(self.contract).rsplit("/", 1)[-1])

    def advertised_state(self):
        """Existence and identity of the external contract path; contents unread."""
        try:
            info = self.advertised_directory.lstat()
        except OSError:
            return {"exists": False}
        return {"exists": True,
                "identity": (info.st_dev, info.st_ino, info.st_mode,
                             info.st_uid, info.st_size)}

    def stdout_text(self):
        return ANSWER + "FABRIC_ARTIFACTS_V1 " + canonical(self.manifest_for_stdout()).decode() + "\n"

    def manifest_for_stdout(self):
        return dict(schema="mastermind.fabric_artifact_manifest.v1",
                    request_sha256=sha(canonical(self.contract)),
                    root=ROOT, parent=PARENT, run_id=RUN_ID, host=HOST,
                    files=[{"path": path, "bytes": (self.artifact_dir / Path(path).name).stat().st_size,
                            "sha256": sha((self.artifact_dir / Path(path).name).read_bytes())}
                           for path in self.production.paths(self.contract)])

    def process_row(self):
        stdout = self.stdout_text().encode()
        row = {
            "schema": "mastermind.local_owned_process_receipt.v1", "label": RUN_ID,
            "returncode": 0, "timed_out": False, "pid": 4242, "pgid": 4242,
            "stdout_bytes": len(stdout), "stderr_bytes": 0,
            "stdout_truncated": False, "stderr_truncated": False,
            "started_at": "2026-10-20T00:00:00Z", "ended_at": "2026-10-20T00:01:00Z",
            "runtime_failure_code": None, "stdout_sha256": sha(stdout),
            "cleanup": {"identity_verified": True, "census_proven": True,
                        "residual_count": 0, "status": "not_needed", "error_code": None,
                        "stdin_delivery_complete": True, "stdin_delivery_error": None,
                        "stdout_capture_complete": True, "stdout_capture_error": None,
                        "stderr_capture_complete": True, "stderr_capture_error": None},
            "artifact_production": {
                "schema": "mastermind.fabric_artifact_completion.v1", "mode": "glm",
                "contract": dict(self.contract), "manifest": self.manifest_for_stdout(),
                "stdout_sha256": sha(stdout)},
        }
        return canonical(row) + b"\n"

    def log_head(self, stamp):
        return f"{stamp} [remote_sub id={RUN_ID} host={HOST}] "

    def prelaunch_log(self):
        head = self.log_head("2026-10-20T00:00Z")
        exclusive(self.log_path, "".join(line + "\n" for line in (
            head + "RUN_RESERVED explicit=1",
            head + "LEASE_OK pool=glm",
            head + f"SUPPORT_VERSION_READY digest={self.support_digest} policy={POLICY}",
        )).encode())

    def retain_launch_binding(self):
        result = subprocess.run(
            [sys.executable, str(self.ctl / "remote_sub_helpers.py"), "launch-binding",
             str(self.log_path), str(self.packet_pin), str(self.lease_path), RUN_ID,
             ROOT, PARENT, HOST, "glm", MODEL, self.support_digest, LEASE_ID, ALIAS, "-"],
            capture_output=True, text=True, timeout=60, cwd=str(self.ctl))
        assert result.returncode == 0, result.stdout + result.stderr

    def post_launch_log(self):
        head = self.log_head("2026-10-20T00:01Z")
        raw = self.log_path.read_bytes()
        self.log_path.unlink()
        exclusive(self.log_path, raw + "".join(line + "\n" for line in (
            head + f"LAUNCH stdout=lanes_{RUN_ID}.stdout rc_file=ext/lanes_{RUN_ID}.rc cwd=~",
            head + "LAUNCH_ATTEMPT attempt=1",
            head + "REMOTE_DONE rc=0",
            head + "REMOTE_CLEANED transport=1 receipt_saved=1 usage_saved=0",
            head + "DONE rc=0 signal=ok",
        )).encode())

    def write_binding(self):
        sources = {
            "packet": {"path": str(self.packet_pin), "sha256": sha(self.packet_pin.read_bytes())},
            "log": {"path": str(self.log_path), "sha256": sha(self.log_path.read_bytes())},
            "support": {"path": str(self.support_pin),
                        "sha256": sha(self.support_pin.read_bytes())}}
        exclusive(self.binding_path, json.dumps({
            "schema": "mastermind.original_delivery_binding.v1", "run_id": RUN_ID,
            "root": ROOT, "parent": PARENT, "host": HOST, "mode": "glm",
            "requested_model": self.binding_model, "cwd": "~",
            "artifact_names": [NAME],
            "sources": sources}, sort_keys=True, separators=(",", ":")).encode())

    def ssh_shim(self):
        bin_dir = self.base / "bin"
        bin_dir.mkdir(mode=0o700, exist_ok=True)
        shim = bin_dir / "ssh"
        if shim.exists():
            return bin_dir
        script = """#!/usr/bin/env python3
import os, shlex, subprocess, sys
command = shlex.split(sys.argv[-1])
assert command[:4] == ["python3", "-I", "-S", "-c"], command
code = command[4]
wrapper = ("import os, pwd, types\\n"
           "pwd.getpwuid = lambda uid: types.SimpleNamespace("
           "pw_dir=os.environ['INERT_HOME'])\\n"
           "_real_open = os.open\\n"
           "_carrier = os.environ['INERT_ARTIFACT_ROOT']\\n"
           "def _inert_carrier_open(path, *args, **kwargs):\\n"
           "    if path == '/tmp':\\n"
           "        return _real_open(_carrier, *args, **kwargs)\\n"
           "    return _real_open(path, *args, **kwargs)\\n"
           "os.open = _inert_carrier_open\\n"
           "exec(compile(" + repr(code) + ", 'generated-reader', 'exec'))\\n")
sys.exit(subprocess.run([sys.executable, "-I", "-S", "-c", wrapper]).returncode)
"""
        exclusive(shim, script.encode(), 0o700)
        return bin_dir

    def environment(self, bin_dir=None, **extra):
        env = dict(os.environ)
        env["INERT_HOME"] = str(self.home)
        env["INERT_ARTIFACT_ROOT"] = str(self.artifact_root)
        env["CODEX_THREAD_ID"] = ROOT
        env.pop("POOL_ORCHESTRATOR_ID", None)
        env.pop("POOL_PARENT_RUN_ID", None)
        env["POOL_LEDGER_PATH"] = str(self.ledger_path)
        if bin_dir is not None:
            env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH','')}"
        env.update({k: v for k, v in extra.items() if v is not None})
        for key, value in extra.items():
            if value is None:
                env.pop(key, None)
        return env

    # ---- composed operations ----------------------------------------------

    def collect(self, destination=None):
        return self.collector.collect(self.binding_path, run_id=RUN_ID, root=ROOT,
                                      parent=PARENT,
                                      destination=str(destination or self.destination))

    def collect_complete(self, destination=None):
        receipt = self.collect(destination)
        assert receipt["state"] == "COMPLETE", receipt
        return receipt

    def receipt_raw(self, destination=None):
        path = Path(destination or self.destination) / "receipt.json"
        return path.read_bytes()

    def qualify(self, destination=None):
        receipt = Path(destination or self.destination) / "receipt.json"
        return self.collector.retained_collection_quality(
            self.binding_path, collection_receipt=receipt,
            expected_sha256=sha(receipt.read_bytes()),
            run_id=RUN_ID, root=ROOT, parent=PARENT)

    def adjudication_bytes(self, subject, verdict="PASS", by="deterministic",
                           reason="inert deterministic quality adjudication",
                           evidence="retained_complete_collection_readback"):
        row = {"schema": ADJ_SCHEMA, "run_id": subject["run_id"], "root": subject["root"],
               "parent": subject["parent"], "verdict": verdict, "by": by,
               "reason": reason, "evidence": evidence,
               "receipt_sha256": subject["receipt_sha256"],
               "stdout_sha256": subject["stdout"]["sha256"],
               "stdout_bytes": subject["stdout"]["bytes"],
               "files": subject["files"], "artifacts": subject["artifacts"]}
        return canonical(row)

    def write_adjudication(self, subject, verdict="PASS", by="deterministic",
                           path=None, **kwargs):
        raw = self.adjudication_bytes(subject, verdict=verdict, by=by, **kwargs)
        target = Path(path) if path is not None else self.adjudication_path
        if target.exists():
            target.unlink()
        exclusive(target, raw)
        return target

    def record(self, subject=None, verdict="PASS", by="deterministic", **kwargs):
        if subject is None:
            with self.qualify() as qualified:
                subject = qualified.subject
        self.write_adjudication(subject, verdict=verdict, by=by, **kwargs)
        return self.publish()

    def publish(self, *, receipt=None, receipt_sha256=None, binding=None,
                adjudication=None):
        receipt = Path(receipt) if receipt is not None else self.destination / "receipt.json"
        if receipt_sha256 is None:
            receipt_sha256 = sha(receipt.read_bytes())
        return self.ledger.publish_collection_quality(
            run_id=RUN_ID, root=ROOT, parent=PARENT,
            binding=str(binding) if binding is not None else str(self.binding_path),
            collection=str(receipt),
            receipt_sha256=receipt_sha256,
            adjudication_path=(str(adjudication) if adjudication is not None
                               else str(self.adjudication_path)))

    def inspect(self):
        return self.ledger.read_collection_quality(RUN_ID, root=ROOT, parent=PARENT)

    def attested_subject(self):
        """The qualified collected artifact subject the attestation projects."""
        projection = self.inspect()
        if projection["state"] != "RECORDED":
            raise AssertionError("quality attestation not recorded: "
                                 + projection["state"])
        return self.ledger.collection_quality_subject_projection(projection["attestation"])

    def sidecar_paths(self):
        state_dir = Path(self.ledger._collection_quality_state_dir())
        return (state_dir / (RUN_ID + ".collection-quality.json"),
                state_dir / (RUN_ID + ".collection-quality.pending.json"))

    def ledger_bytes(self):
        return self.ledger_path.read_bytes() if self.ledger_path.exists() else b""

    def publish_terminal_row(self, ledger=None, run=RUN_ID, root=ROOT, parent=PARENT):
        owner = ledger if ledger is not None else self.ledger
        return owner.append(pool="glm", key="-", window_id="inert-window",
                            task_class="remote-glm", job_class="execute",
                            run_id=run, root_id=root, parent_run_id=parent,
                            rc=0, signal="ok", reason="inert_terminal",
                            model=MODEL, strict=True,
                            reconciliation={"lease_id": LEASE_ID})

    def write_broker(self, state="released", lease_id=LEASE_ID, account=ALIAS,
                     model=MODEL, pool="glm", task_class="remote-glm", host=HOST):
        directory = self.ctl / "broker"
        directory.mkdir(mode=0o700, exist_ok=True)
        path = directory / "leases.sqlite"
        if path.exists():
            path.unlink()
        db = sqlite3.connect(path)
        try:
            db.execute("CREATE TABLE leases (id TEXT, orchestrator_id TEXT, pool TEXT,"
                       " account TEXT, task_class TEXT, host TEXT, state TEXT, model TEXT)")
            db.execute("INSERT INTO leases VALUES (?,?,?,?,?,?,?,?)",
                       (lease_id, ROOT, pool, account, task_class, host, state, model))
            db.commit()
        finally:
            db.close()
        return path

    def write_controller_proof(self, *, run=RUN_ID, root=ROOT, parent=PARENT,
                               controller_rc=0, prelease=None, mode="body",
                               log_bytes=None, return_extra=None):
        state = self.ctl / "state" / "remote_sub"
        body = self.body if mode == "body" else self.packet
        request = {"schema": "mastermind.fabric_request_artifact.v1", "run_id": run,
                   "root_id": root, "parent_run_id": parent, "task_class": "execute",
                   "cwd": "~", "packet": f"{run}.request.packet",
                   "packet_sha256": sha(body), "packet_bytes": len(body),
                   "created_at": 0.0, "automatic_background_execution": False}
        launch = {"schema": "mastermind.fabric_request_launch.v1", "run_id": run,
                  "root_id": root, "parent_run_id": parent, "packet_sha256": sha(body),
                  "state": "LAUNCH_ATTEMPT_RESERVED", "created_at": 0.0,
                  "request_sha256": sha(canonical(request))}
        request_raw, launch_raw = canonical(request), canonical(launch)
        log_raw = self.log_path.read_bytes() if log_bytes is None else log_bytes
        returned = {"schema": "mastermind.fabric_request_return.v1", "run_id": run,
                    "root_id": root, "parent_run_id": parent,
                    "state": "NATIVE_CONTROLLER_RETURNED", "controller_rc": controller_rc,
                    "request_sha256": sha(request_raw), "launch_sha256": sha(launch_raw),
                    "prelease_sha256": prelease, "log_sha256": sha(log_raw)}
        if return_extra:
            returned.update(return_extra)
        for name, data in ((f"{run}.request.packet", body),
                           (f"{run}.request.json", request_raw),
                           (f"{run}.request-launch.json", launch_raw),
                           (f"{run}.request-return.json", canonical(returned))):
            target = state / name
            if target.exists():
                target.unlink()
            exclusive(target, data)
        return {"request": request_raw, "launch": launch_raw, "return": canonical(returned)}

    def race_on_reverify(self, mutate, on_calls):
        """Patch the collector qualification for deterministic race injection.

        The wrapped qualification behaves identically except that the chosen
        reverify calls (1 = before the sidecar link, 2 = after link, fsync and
        readback) apply the mutation first, exactly like a concurrent source
        mutation inside the publication window.
        """
        original = self.collector.retained_collection_quality
        state = {"n": 0}

        class Wrapped:
            def __init__(self, *args, **kwargs):
                self._inner = original(*args, **kwargs)

            def __enter__(self):
                qualified = self._inner.__enter__()
                base = qualified.reverify

                def reverify():
                    state["n"] += 1
                    if state["n"] in on_calls:
                        mutate()
                    return base()

                qualified.reverify = reverify
                return qualified

            def __exit__(self, *exc):
                return self._inner.__exit__(*exc)

        self.collector.retained_collection_quality = Wrapped
        return original

    @staticmethod
    def race_on_owner_read(target, mutate):
        """Patch the incumbent owner read for deterministic race injection.

        The wrapped read behaves identically except that, the first time the
        chosen file's bytes come back, the mutation runs — exactly like a
        concurrent same-bytes replacement landing inside the owner-read window
        instead of at a controlled reverify point.
        """
        import artifact_delivery as delivery_module
        original = delivery_module.read_local_at
        state = {"n": 0}

        def read_local_at(chain, name, limit):
            raw = original(chain, name, limit)
            if name == target and state["n"] == 0:
                state["n"] += 1
                mutate()
            return raw

        delivery_module.read_local_at = read_local_at
        return original

    @staticmethod
    def restore_owner_read(original):
        import artifact_delivery as delivery_module
        delivery_module.read_local_at = original

    def cli(self, *args, **env_extra):
        return subprocess.run(
            [sys.executable, str(self.ctl / "fabric_task.py"), *args],
            capture_output=True, text=True, timeout=120,
            env=self.environment(self.ssh_shim() if env_extra.pop("shim", True) else None,
                                 **env_extra), cwd=str(self.ctl))

    def cleanup(self):
        shutil.rmtree(self.artifact_root, ignore_errors=True)


def stack(prefix):
    base = os.environ.get("NATIVE_ROLLOUT_TEST_ROOT", str(Path.home()))
    return tempfile.TemporaryDirectory(prefix=prefix, dir=base)


_MODULE_NAMES = ("artifact_reader", "artifact_production", "native_runtime_bindings",
                 "artifact_delivery", "original_delivery_collector", "remote_sub_helpers",
                 "pool_ledger", "fabric_task", "native_completion_reconcile", "model_tier",
                 "pick", "lane_runtime", "a04_terminal_reconcile",
                 "native_prestart_reconcile", "native_preexec_reconcile",
                 "native_host_review_controller_reconcile")

_ENV_KEYS = ("CODEX_THREAD_ID", "POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID",
             "POOL_LEDGER_PATH", "INERT_HOME", "INERT_ARTIFACT_ROOT", "PATH")


class fixture_stack:
    """One independent fixture install: private modules, env and cleanup.

    Each install owns its own module instances; entering snapshots and exiting
    restores the surrounding install's sys.modules entries so a nested fixture
    can never re-point an outer fixture's lazy owner imports.
    """

    def __init__(self, prefix, **fixture_kwargs):
        self._prefix = prefix
        self._fixture_kwargs = fixture_kwargs
        self._stack = None
        self._fx = None

    def __enter__(self):
        self._saved_env = {key: os.environ.get(key) for key in _ENV_KEYS}
        self._saved_modules = {name: sys.modules.get(name) for name in _MODULE_NAMES}
        self._stack = stack(self._prefix)
        self._fx = Fixture(self._stack, **self._fixture_kwargs)
        return self._fx

    def __exit__(self, *_):
        if self._fx is not None:
            self._fx.cleanup()
        for name, module in self._saved_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._stack.cleanup()
        return False


class QualityCase(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in
                       ("CODEX_THREAD_ID", "POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID",
                        "POOL_LEDGER_PATH", "INERT_HOME", "INERT_ARTIFACT_ROOT", "PATH")}
        self._stack = stack("collection-quality-")
        self.fx = Fixture(self._stack)
        os.environ["CODEX_THREAD_ID"] = ROOT
        os.environ.pop("POOL_ORCHESTRATOR_ID", None)
        os.environ.pop("POOL_PARENT_RUN_ID", None)
        os.environ["POOL_LEDGER_PATH"] = str(self.fx.ledger_path)
        self.fx.ledger.LEDGER_PATH = str(self.fx.ledger_path)
        self.fx.ledger.LEDGER_DIR = str(self.fx.base)

    def tearDown(self):
        if getattr(self, "fx", None) is not None:
            self.fx.cleanup()
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._stack.cleanup()

    def set_env(self, **values):
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    # ---- forward-only positive path -------------------------------------

    def test_full_artifact_collection_qualifies_and_publishes_sidecar(self):
        receipt = self.fx.collect_complete()
        self.assertTrue(receipt["delivery_verified"])
        self.assertTrue(receipt["worker_terminal_proof"])
        # Exact advertised artifact paths are preserved by the owner seam even
        # though the fixture bytes live in a private fixture-owned root. The
        # advertised external contract directory itself is never created,
        # adopted, modified or removed: on a host where an earlier synthetic
        # fixture left it, it is still there, unchanged, after this whole
        # collect → qualify → publish lifecycle.
        self.assertEqual([item["path"] for item in self.fx.manifest["files"]],
                         self.fx.production.paths(self.fx.contract))
        self.assertEqual(self.fx.advertised_state(), self.fx.advertised_before)
        with self.fx.qualify() as qualified:
            subject = qualified.subject
            self.assertEqual(subject["schema"], "mastermind.collection_quality_subject.v1")
            self.assertEqual(subject["host"], HOST)
            self.assertEqual(subject["mode"], "glm")
            self.assertEqual(subject["artifact_names"], [NAME])
            self.assertEqual(subject["returncode"], 0)
            self.assertEqual([item["local_name"] for item in subject["artifacts"]],
                             ["artifact.00"])
            # Held-descriptor revalidation accepts the unchanged collection and
            # stays provable while the descriptors are held.
            self.assertTrue(qualified.reverify())
            outcome = self.fx.record(subject)
        self.assertEqual(outcome["state"], "RECORDED")
        self.assertFalse(outcome["idempotent"])
        self.assertEqual(outcome["collected_source_quality"], "PASS")
        self.assertEqual(outcome["quality_by"], "deterministic")
        projection = self.fx.inspect()
        self.assertEqual(projection["state"], "RECORDED")
        self.assertEqual(projection["collected_source_quality"], "PASS")
        attestation = projection["attestation"]
        self.assertEqual(attestation["schema"], QUALITY_SCHEMA)
        self.assertEqual(attestation["root"], ROOT)
        self.assertEqual(attestation["parent"], PARENT)
        self.assertNotIn("accepted_by", attestation)
        self.assertNotIn("acceptance", attestation)
        self.assertNotIn("terminal", attestation)
        self.assertEqual(attestation["collection"]["delivery_verified"], True)
        self.assertEqual(attestation["collection"]["worker_terminal_proof"], True)
        self.assertEqual(attestation["collection"]["returncode"], 0)
        # Every artifact digest/length/name is bound.
        self.assertEqual(attestation["collection"]["artifacts"], subject["artifacts"])
        self.assertEqual(attestation["source"]["packet_sha256"], sha(self.fx.packet))
        self.assertEqual(attestation["source"]["body_sha256"],
                         self.fx.contract["body_sha256"])
        self.assertEqual(attestation["source"]["support_digest"],
                         self.fx.support_digest)
        # The complete explicit adjudication is retained and re-hashes to the
        # attested digest, so the readback is closed over the real input.
        record = attestation["adjudication"]["record"]
        self.assertEqual(sha(record.encode("utf-8")),
                         attestation["adjudication"]["adjudication_sha256"])
        self.assertEqual(canonical(json.loads(record)),
                         self.fx.adjudication_bytes(subject).replace(b"\n", b""))
        # The sidecar lives in the owner state directory, never in the collection.
        self.assertTrue(str(outcome["path"]).startswith(str(self.fx.ctl / "state/remote_sub/")))
        self.assertFalse((self.fx.destination / "collection-quality.json").exists())

    def test_duplicate_publication_is_idempotent_and_ledger_bytes_unchanged(self):
        self.fx.collect_complete()
        self.fx.record()
        before = self.fx.ledger_bytes()
        outcome = self.fx.record()
        self.assertEqual(outcome["state"], "RECORDED")
        self.assertTrue(outcome["idempotent"])
        self.assertEqual(self.fx.ledger_bytes(), before)
        # Inspection is read-only as well.
        self.fx.inspect()
        self.assertEqual(self.fx.ledger_bytes(), before)

    def test_owner_rejects_raw_subject_publication_bypass(self):
        self.fx.collect_complete()
        with self.fx.qualify() as qualified:
            subject = qualified.subject
        adjudication = self.fx.adjudication_bytes(subject)
        # The old raw-subject / optional-callback publication shape no longer
        # exists: any attempt is a TypeError before any input is read.
        for kwargs in (
                {"subject": subject, "adjudication": {"verdict": "PASS"}},
                {"subject": subject, "adjudication": {"verdict": "PASS"}, "verify": lambda: None},
                {"adjudication_path": str(self.fx.adjudication_path)},
        ):
            with self.assertRaises(TypeError):
                self.fx.ledger.publish_collection_quality(
                    run_id=RUN_ID, root=ROOT, parent=PARENT, **kwargs)
        # Path-typed inputs that do not exist refuse without publishing.
        missing = self.fx.base / "absent"
        with self.assertRaises(ValueError):
            self.fx.ledger.publish_collection_quality(
                run_id=RUN_ID, root=ROOT, parent=PARENT,
                binding=str(missing / "binding.json"),
                collection=str(missing / "receipt.json"),
                receipt_sha256="0" * 64,
                adjudication_path=str(missing / "adjudication.json"))
        canonical_path, pending_path = self.fx.sidecar_paths()
        self.assertFalse(canonical_path.exists())
        self.assertFalse(pending_path.exists())

    def test_changed_subject_adjudication_or_destination_conflicts_without_overwrite(self):
        self.fx.collect_complete()
        original = self.fx.record()
        canonical_path = Path(original["path"])
        recorded = canonical_path.read_bytes()
        recorded_inode = os.stat(canonical_path).st_ino
        with self.fx.qualify() as qualified:
            subject = qualified.subject
        # A different verdict is an explicit conflict.
        with self.assertRaises(self.fx.ledger.CollectionQualityConflict):
            self.fx.record(subject, verdict="FAIL")
        # A changed adjudication basis is a conflict.
        self.fx.write_adjudication(subject, reason="different adjudication basis")
        with self.assertRaises(self.fx.ledger.CollectionQualityConflict):
            self.fx.publish()
        # A changed destination is a conflict: same bytes elsewhere bind a
        # different subject destination.
        moved = self.fx.dest_root / "runs" / "moved-collection"
        shutil.copytree(self.fx.destination, moved)
        try:
            with self.assertRaises(self.fx.ledger.CollectionQualityConflict):
                self.fx.publish(receipt=moved / "receipt.json")
        finally:
            shutil.rmtree(moved, ignore_errors=True)
        # A claimed different receipt digest refuses qualification outright.
        with self.assertRaises(ValueError):
            self.fx.publish(receipt_sha256="f" * 64)
        # A caller scope mismatch refuses before publication.
        with self.assertRaises(ValueError):
            self.fx.ledger.publish_collection_quality(
                run_id=RUN_ID, root=ROOT, parent="other-parent",
                binding=str(self.fx.binding_path),
                collection=str(self.fx.destination / "receipt.json"),
                receipt_sha256=sha(self.fx.receipt_raw()),
                adjudication_path=str(self.fx.adjudication_path))
        self.assertEqual(canonical_path.read_bytes(), recorded)
        self.assertEqual(os.stat(canonical_path).st_ino, recorded_inode)
        self.assertEqual(self.fx.inspect()["collected_source_quality"], "PASS")

    def test_concurrent_publications_have_one_authoritative_winner(self):
        self.fx.collect_complete()
        with self.fx.qualify() as qualified:
            subject = qualified.subject
        moved = self.fx.dest_root / "runs" / "second-collection"
        shutil.copytree(self.fx.destination, moved)
        try:
            other_receipt = moved / "receipt.json"
            self.fx.write_adjudication(subject, path=self.fx.base / "adj-a.json")
            self.fx.write_adjudication(subject, path=self.fx.base / "adj-b.json")
            results, errors = [], []

            def publish(receipt_path, adjudication_path):
                try:
                    results.append(self.fx.ledger.publish_collection_quality(
                        run_id=RUN_ID, root=ROOT, parent=PARENT,
                        binding=str(self.fx.binding_path),
                        collection=str(receipt_path),
                        receipt_sha256=sha(Path(receipt_path).read_bytes()),
                        adjudication_path=str(adjudication_path)))
                except Exception as exc:  # noqa: BLE001 - the typed refusal is the result
                    errors.append(exc)

            threads = [threading.Thread(target=publish, args=(
                            self.fx.destination / "receipt.json", self.fx.base / "adj-a.json")),
                       threading.Thread(target=publish, args=(
                            other_receipt, self.fx.base / "adj-b.json"))]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(len(results), 1)
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], self.fx.ledger.CollectionQualityConflict)
            winner = self.fx.inspect()
            self.assertEqual(winner["state"], "RECORDED")
            self.assertIn(winner["attestation"]["collection"]["destination"],
                          {str(self.fx.destination), str(moved)})
        finally:
            shutil.rmtree(moved, ignore_errors=True)

    def test_distinct_verdicts_record_distinctly_and_flip_conflicts(self):
        seen = []
        for verdict in ("PASS", "FAIL", "PARTIAL"):
            with fixture_stack("collection-quality-verdict-") as fx:
                fx.collect_complete()
                outcome = fx.record(verdict=verdict)
                self.assertEqual(outcome["state"], "RECORDED")
                projection = fx.inspect()
                self.assertEqual(projection["collected_source_quality"], verdict)
                seen.append(projection["attestation"]["collected_source_quality"])
                if verdict != "PASS":
                    continue
                with self.assertRaises(fx.ledger.CollectionQualityConflict):
                    fx.record(verdict="FAIL")
                self.assertEqual(fx.inspect()["collected_source_quality"], "PASS")
        self.assertEqual(seen, ["PASS", "FAIL", "PARTIAL"])

    # ---- caller guard -----------------------------------------------------

    def test_caller_guard_allows_unset_optional_labels_and_refuses_mismatch(self):
        self.fx.collect_complete()
        # The legitimate native shell carries POOL_ORCHESTRATOR_ID unset: the
        # optional labels are never required, only refused on mismatch.
        self.set_env(POOL_ORCHESTRATOR_ID=None, POOL_PARENT_RUN_ID=None)
        with self.fx.qualify() as qualified:
            subject = qualified.subject
        outcome = self.fx.record(subject)
        self.assertEqual(outcome["state"], "RECORDED")
        self.assertEqual(self.fx.inspect()["state"], "RECORDED")

    def test_caller_guard_refuses_before_any_read(self):
        self.fx.collect_complete()
        missing = self.fx.dest_root / "runs" / "absent" / "receipt.json"
        cases = [
            ({"CODEX_THREAD_ID": "child-thread-1"}, "quality_caller_not_original_root"),
            ({"CODEX_THREAD_ID": ROOT, "POOL_ORCHESTRATOR_ID": "coordinator-9"},
             "quality_caller_coordinator_label_mismatch"),
            ({"CODEX_THREAD_ID": ROOT, "POOL_ORCHESTRATOR_ID": ROOT,
              "POOL_PARENT_RUN_ID": "other-parent"}, "quality_caller_parent_label_mismatch"),
        ]
        for extra, reason in cases:
            self.set_env(**extra)
            try:
                with self.assertRaises(self.fx.collector.OriginalDeliveryRefused) as caught:
                    self.fx.collector.retained_collection_quality(
                        self.fx.binding_path, collection_receipt=missing,
                        expected_sha256="0" * 64, run_id=RUN_ID, root=ROOT, parent=PARENT
                    ).__enter__()
                self.assertEqual(caught.exception.reason, reason)
            finally:
                self.set_env(CODEX_THREAD_ID=ROOT, POOL_ORCHESTRATOR_ID=None,
                             POOL_PARENT_RUN_ID=None)
        # Labels alone never authenticate: the guard also fires before IO when
        # the claimed root is foreign even with a well-formed receipt present.
        raw = self.fx.receipt_raw()
        with self.assertRaises(self.fx.collector.OriginalDeliveryRefused):
            self.fx.collector.retained_collection_quality(
                self.fx.binding_path,
                collection_receipt=self.fx.destination / "receipt.json",
                expected_sha256=sha(raw), run_id=RUN_ID, root="other-root-1",
                parent=PARENT).__enter__()

    def test_plain_and_historical_scopes_are_refused(self):
        self.fx.collect_complete()
        raw = self.fx.receipt_raw()
        # Historical exception scope names are refused without any read.
        for scope in self.fx.collector.PLAIN_SCOPES:
            with self.assertRaises(self.fx.collector.OriginalDeliveryRefused):
                self.fx.collector.retained_collection_quality(
                    self.fx.binding_path,
                    collection_receipt=self.fx.destination / "receipt.json",
                    expected_sha256=sha(raw), run_id=scope, root=ROOT,
                    parent=PARENT).__enter__()
        # A plain binding (no artifact contract) is refused.
        plain_dir = self.fx.base / "plain-collection"
        plain_dir.mkdir(mode=0o700)
        plain_binding = self.fx.base / "plain-binding.json"
        sources = {
            "packet": {"path": str(self.fx.ctl / f"state/remote_sub/{RUN_ID}.request.packet"),
                       "sha256": sha(self.fx.body)},
            "log": {"path": str(self.fx.log_path), "sha256": sha(self.fx.log_path.read_bytes())},
            "support": {"path": str(self.fx.support_pin),
                        "sha256": sha(self.fx.support_pin.read_bytes())}}
        exclusive(self.fx.ctl / f"state/remote_sub/{RUN_ID}.request.packet", self.fx.body)
        for item in self.fx.destination.iterdir():
            shutil.copyfile(item, plain_dir / item.name)
        exclusive(plain_binding, json.dumps({
            "schema": "mastermind.original_delivery_binding.v1", "run_id": RUN_ID,
            "root": ROOT, "parent": PARENT, "host": HOST, "mode": "glm",
            "requested_model": MODEL, "cwd": "~", "artifact_names": [],
            "sources": sources}, sort_keys=True, separators=(",", ":")).encode())
        receipt = json.loads(raw)
        receipt["artifact_names"] = []
        with self.assertRaises(self.fx.collector.OriginalDeliveryRefused) as caught:
            self.fx.collector.retained_collection_quality(
                plain_binding, collection_receipt=plain_dir / "receipt.json",
                expected_sha256=sha(raw), run_id=RUN_ID, root=ROOT,
                parent=PARENT).__enter__()
        self.assertEqual(caught.exception.reason, "quality_binding_unqualified")

    # ---- tamper negatives --------------------------------------------------

    def test_tampered_evidence_refuses_with_distinct_reasons(self):
        self.fx.collect_complete()

        def fresh_collection():
            with fixture_stack("collection-quality-tamper-") as fx:
                fx.collect_complete()
                yield fx

        # Wrong receipt digest.
        with self.assertRaises(self.fx.collector.OriginalDeliveryRefused) as caught:
            self.fx.collector.retained_collection_quality(
                self.fx.binding_path,
                collection_receipt=self.fx.destination / "receipt.json",
                expected_sha256="0" * 64, run_id=RUN_ID, root=ROOT,
                parent=PARENT).__enter__()
        self.assertEqual(caught.exception.reason, "quality_receipt_digest_mismatch")
        # Missing receipt.
        with self.assertRaises(self.fx.collector.OriginalDeliveryRefused) as caught:
            self.fx.collector.retained_collection_quality(
                self.fx.binding_path,
                collection_receipt=self.fx.dest_root / "runs" / "absent" / "receipt.json",
                expected_sha256="0" * 64, run_id=RUN_ID, root=ROOT,
                parent=PARENT).__enter__()
        self.assertEqual(caught.exception.reason, "quality_receipt_unreadable")

        for fx, mutate, expected in (
                ("stdout", lambda fx: (fx.destination / "stdout.000").write_bytes(b"tampered\n"),
                 "quality_collection_readback_unqualified"),
                ("artifact", lambda fx: (fx.destination / "artifact.00").write_bytes(b"tampered"),
                 "quality_collection_readback_unqualified"),
                ("omitted-artifact", lambda fx: (fx.destination / "artifact.00").unlink(),
                 "quality_collection_readback_unqualified"),
                ("packet", lambda fx: (fx.packet_pin).write_bytes(self.fx.packet + b"x"),
                 "quality_binding_unqualified"),
                ("binding", lambda fx: (fx.destination / "binding.json").write_bytes(b"{}"),
                 "quality_collection_readback_unqualified")):
            with self.subTest(tamper=mutate):
                for fx_instance in fresh_collection():
                    raw = fx_instance.receipt_raw()
                    mutate(fx_instance)
                    with self.assertRaises(fx_instance.collector.OriginalDeliveryRefused) as caught:
                        fx_instance.collector.retained_collection_quality(
                            fx_instance.binding_path,
                            collection_receipt=fx_instance.destination / "receipt.json",
                            expected_sha256=sha(raw), run_id=RUN_ID, root=ROOT,
                            parent=PARENT).__enter__()
                    self.assertEqual(caught.exception.reason, expected)

        # A receipt with a foreign host (digest recomputed) refuses on scope.
        receipt = json.loads(self.fx.receipt_raw())
        receipt["host"] = "other-host"
        tampered = self.fx.destination / "receipt.json"
        tampered.unlink()
        exclusive(tampered, canonical(receipt))
        with self.assertRaises(self.fx.collector.OriginalDeliveryRefused) as caught:
            self.fx.collector.retained_collection_quality(
                self.fx.binding_path, collection_receipt=tampered,
                expected_sha256=sha(tampered.read_bytes()), run_id=RUN_ID,
                root=ROOT, parent=PARENT).__enter__()
        self.assertEqual(caught.exception.reason, "quality_receipt_scope_mismatch")

    def test_adjudication_must_close_over_the_whole_subject(self):
        self.fx.collect_complete()
        with self.fx.qualify() as qualified:
            subject = qualified.subject

        def refused(raw, expected):
            with self.assertRaises(self.fx.collector.OriginalDeliveryRefused) as caught:
                self.fx.collector.quality_adjudication(raw, subject=subject)
            self.assertEqual(caught.exception.reason, expected)

        refused(b'{"ok":true}', "quality_adjudication_incomplete")
        refused(b"not json", "quality_adjudication_invalid")
        refused(b"", "quality_adjudication_invalid")

        def row(**changes):
            value = json.loads(self.fx.adjudication_bytes(subject))
            value.update(changes)
            for key, removal in changes.items():
                if removal is None:
                    value.pop(key, None)
            return canonical(value)

        refused(row(verdict="EXCELLENT"), "quality_adjudication_incomplete")
        refused(row(by="worker"), "quality_adjudication_incomplete")
        refused(row(stdout_sha256="0" * 64), "quality_adjudication_incomplete")
        refused(row(stdout_bytes=1), "quality_adjudication_incomplete")
        refused(row(receipt_sha256="0" * 64), "quality_adjudication_incomplete")
        refused(row(files=[]), "quality_adjudication_incomplete")
        refused(row(artifacts=[]), "quality_adjudication_incomplete")
        refused(row(run_id="other-run"), "quality_adjudication_incomplete")
        refused(row(reason=None), "quality_adjudication_incomplete")
        refused(row(evidence=None), "quality_adjudication_incomplete")
        extra = json.loads(self.fx.adjudication_bytes(subject))
        extra["artifacts"] = subject["artifacts"] + [dict(subject["artifacts"][0])]
        refused(canonical(extra), "quality_adjudication_incomplete")
        extra = json.loads(self.fx.adjudication_bytes(subject))
        extra["extra_field"] = "x"
        refused(canonical(extra), "quality_adjudication_incomplete")
        normalized = self.fx.collector.quality_adjudication(
            self.fx.adjudication_bytes(subject), subject=subject)
        self.assertEqual(normalized["verdict"], "PASS")
        self.assertEqual(normalized["by"], "deterministic")
        self.assertEqual(normalized["adjudication_sha256"],
                         sha(self.fx.adjudication_bytes(subject)))

    # ---- retained descriptors and publication hazards ----------------------

    def test_same_bytes_replacement_between_qualification_and_link_refuses(self):
        self.fx.collect_complete()
        chunk = self.fx.destination / "stdout.000"
        original = chunk.read_bytes()

        def replace_with_identical_bytes():
            chunk.unlink()
            exclusive(chunk, original)

        saved = self.fx.race_on_reverify(replace_with_identical_bytes, {1})
        try:
            with self.assertRaises(ValueError) as caught:
                self.fx.record()
            self.assertIn("qualified_collection_changed", str(caught.exception))
        finally:
            self.fx.collector.retained_collection_quality = saved
        canonical_path, pending_path = self.fx.sidecar_paths()
        self.assertFalse(canonical_path.exists())
        # The failed attempt leaves its own invalidated pending inode only.
        self.assertTrue(pending_path.exists())
        self.assertEqual(pending_path.read_bytes(), b"")
        self.assertEqual(self.fx.inspect()["state"], "STAGED_UNPUBLISHED")

    def test_mutation_before_link_refuses_and_is_reported_staged(self):
        self.fx.collect_complete()
        chunk = self.fx.destination / "stdout.000"
        original = chunk.read_bytes()

        def append_after_qualification():
            chunk.unlink()
            exclusive(chunk, original + b"appended\n")

        saved = self.fx.race_on_reverify(append_after_qualification, {1})
        try:
            with self.assertRaises(ValueError):
                self.fx.record()
        finally:
            self.fx.collector.retained_collection_quality = saved
        canonical_path, pending_path = self.fx.sidecar_paths()
        self.assertFalse(canonical_path.exists())
        self.assertTrue(pending_path.exists())
        self.assertEqual(pending_path.read_bytes(), b"")
        projection = self.fx.inspect()
        self.assertEqual(projection["state"], "STAGED_UNPUBLISHED")
        self.assertNotIn("collected_source_quality", projection)
        # Restoring the collection does not authorize a blind retry: the
        # retained pending name still refuses under the fixed receipt owner.
        chunk.unlink()
        exclusive(chunk, original)
        with self.assertRaises(self.fx.ledger.CollectionQualityAmbiguous):
            self.fx.record()

    def test_previous_confirmed_attestation_survives_repeated_conflicts(self):
        self.fx.collect_complete()
        confirmed = self.fx.record()
        canonical_path = Path(confirmed["path"])
        pending_path = canonical_path.with_name(RUN_ID + ".collection-quality.pending.json")
        confirmed_bytes = canonical_path.read_bytes()
        confirmed_inode = os.stat(canonical_path).st_ino
        pending_inode = os.stat(pending_path).st_ino
        # A conflicting publication never touches the confirmed inode pair.
        for verdict in ("FAIL", "PARTIAL"):
            with self.assertRaises(self.fx.ledger.CollectionQualityConflict):
                self.fx.record(verdict=verdict)
            self.assertEqual(canonical_path.read_bytes(), confirmed_bytes)
            self.assertEqual(os.stat(canonical_path).st_ino, confirmed_inode)
            self.assertEqual(os.stat(pending_path).st_ino, pending_inode)
        # Readback still projects only the confirmed attestation, never a
        # refused attempt, and reports the retained staging link.
        projection = self.fx.inspect()
        self.assertEqual(projection["state"], "RECORDED")
        self.assertTrue(projection["staged_retained"])
        self.assertEqual(projection["collected_source_quality"], "PASS")

    def test_post_link_verify_failure_is_fail_closed_and_never_positive(self):
        self.fx.collect_complete()
        state_dir = Path(self.fx.ledger._collection_quality_state_dir())
        retained = {path.name: (sha(path.read_bytes()), os.stat(path).st_ino)
                    for path in state_dir.iterdir()}
        chunk = self.fx.destination / "stdout.000"
        original = chunk.read_bytes()

        def mutate_after_link():
            chunk.unlink()
            exclusive(chunk, original + b"appended\n")

        saved = self.fx.race_on_reverify(mutate_after_link, {2})
        try:
            with self.assertRaises(ValueError):
                self.fx.record()
        finally:
            self.fx.collector.retained_collection_quality = saved
        canonical_path, pending_path = self.fx.sidecar_paths()
        # The link happened, so the canonical name exists — but the one inode
        # this publication created was invalidated through the retained
        # descriptor: no fabricated positive is reachable under either name.
        self.assertTrue(canonical_path.exists())
        self.assertEqual(canonical_path.read_bytes(), b"")
        self.assertEqual(pending_path.read_bytes(), b"")
        projection = self.fx.inspect()
        self.assertEqual(projection["state"], "CANONICAL_UNREADABLE")
        self.assertNotIn("collected_source_quality", projection)
        self.assertNotIn("attestation", projection)
        # No other retained owner file was touched by the invalidation.
        for name, (digest, inode) in retained.items():
            current = state_dir / name
            self.assertEqual(sha(current.read_bytes()), digest, name)
            self.assertEqual(os.stat(current).st_ino, inode, name)
        # A blind retry stays refused under the same fixed receipt owner: the
        # invalidated canonical name is occupied by non-attestation bytes and
        # is never overwritten or fabricated into a positive.
        chunk.unlink()
        exclusive(chunk, original)
        with self.assertRaises(self.fx.ledger.CollectionQualityConflict):
            self.fx.record()
        self.assertEqual(canonical_path.read_bytes(), b"")

    def test_staged_pending_is_retained_and_never_retried_blind(self):
        self.fx.collect_complete()
        state_dir = Path(self.fx.ledger._collection_quality_state_dir())
        pending = state_dir / (RUN_ID + ".collection-quality.pending.json")
        canonical_path = state_dir / (RUN_ID + ".collection-quality.json")
        exclusive(pending, (json.dumps({"schema": QUALITY_SCHEMA, "run_id": RUN_ID},
                                       sort_keys=True, separators=(",", ":")) + "\n").encode())
        before = pending.read_bytes()
        with self.assertRaises(self.fx.ledger.CollectionQualityAmbiguous):
            self.fx.record()
        self.assertFalse(canonical_path.exists())
        self.assertEqual(pending.read_bytes(), before)
        projection = self.fx.inspect()
        self.assertEqual(projection["state"], "STAGED_UNPUBLISHED")
        self.assertEqual(projection["staged_sha256"], sha(before))
        self.assertNotIn("attestation", projection)

    def test_partial_pending_is_retained_and_reported(self):
        self.fx.collect_complete()
        state_dir = Path(self.fx.ledger._collection_quality_state_dir())
        pending = state_dir / (RUN_ID + ".collection-quality.pending.json")
        exclusive(pending, b'{"schema":"mastermind.collection_quality_att')
        with self.assertRaises(self.fx.ledger.CollectionQualityAmbiguous):
            self.fx.record()
        self.assertFalse((state_dir / (RUN_ID + ".collection-quality.json")).exists())
        self.assertTrue(pending.exists())
        projection = self.fx.inspect()
        self.assertEqual(projection["state"], "STAGED_UNPUBLISHED")
        self.assertEqual(projection["staged_schema"], "UNREADABLE")

    def test_uncertain_ack_reconciles_confirmed_canonical_bytes(self):
        self.fx.collect_complete()
        outcome = self.fx.record()
        self.assertEqual(outcome["state"], "RECORDED")
        canonical_path, pending_path = self.fx.sidecar_paths()
        # The staging link is retained as evidence after the link; the caller's
        # acknowledgement is the only place the return code ever lived. A lost
        # acknowledgement is reconciled by reading the confirmed bytes.
        self.assertTrue(pending_path.exists())
        self.assertEqual(os.stat(pending_path).st_ino, os.stat(canonical_path).st_ino)
        projection = self.fx.inspect()
        self.assertEqual(projection["state"], "RECORDED")
        self.assertTrue(projection["staged_retained"])
        self.assertEqual(projection["attestation_sha256"],
                         sha(canonical_path.read_bytes()))
        repeat = self.fx.record()
        self.assertEqual(repeat["state"], "RECORDED")
        self.assertTrue(repeat["idempotent"])

    def test_symlink_and_unsafe_mode_refuse(self):
        self.fx.collect_complete()
        linked = self.fx.base / "linked-receipt.json"
        linked.unlink(missing_ok=True)
        os.symlink(self.fx.destination / "receipt.json", linked)
        with self.assertRaises(self.fx.collector.OriginalDeliveryRefused):
            self.fx.collector.retained_collection_quality(
                self.fx.binding_path, collection_receipt=linked,
                expected_sha256=sha(self.fx.receipt_raw()), run_id=RUN_ID,
                root=ROOT, parent=PARENT).__enter__()
        receipt = self.fx.destination / "receipt.json"
        os.chmod(receipt, 0o606)
        try:
            with self.assertRaises(self.fx.collector.OriginalDeliveryRefused):
                self.fx.collector.retained_collection_quality(
                    self.fx.binding_path, collection_receipt=receipt,
                    expected_sha256=sha(self.fx.receipt_raw()), run_id=RUN_ID,
                    root=ROOT, parent=PARENT).__enter__()
        finally:
            os.chmod(receipt, 0o600)

    def test_same_bytes_replacement_inside_owner_read_refuses_qualification(self):
        """A same-bytes swap inside the owner-read window never qualifies.

        The retained descriptor is held and qualified before the owner read, so
        a replacement that lands between the owner's bytes and the held capture
        leaves the held and visible identities disagreeing: the replacement
        inode is refused and no sidecar positive is reachable.
        """
        self.fx.collect_complete()
        chunk = self.fx.destination / "receipt.json"
        original = chunk.read_bytes()

        def replace_with_identical_bytes():
            chunk.unlink()
            exclusive(chunk, original)

        saved = self.fx.race_on_owner_read("receipt.json",
                                           replace_with_identical_bytes)
        try:
            with self.assertRaises(self.fx.collector.OriginalDeliveryRefused) as caught:
                self.fx.record()
            self.assertEqual(caught.exception.reason,
                             "quality_retained_source_changed")
        finally:
            self.fx.restore_owner_read(saved)
        canonical_path, pending_path = self.fx.sidecar_paths()
        self.assertFalse(canonical_path.exists())
        self.assertFalse(pending_path.exists())
        self.assertEqual(self.fx.inspect()["state"], "NOT_RECORDED")
        # The same collection still qualifies once nothing replaces it.
        outcome = self.fx.record()
        self.assertEqual(outcome["state"], "RECORDED")

    def test_unsafe_retained_input_mode_or_symlink_refuses(self):
        """Held-descriptor qualification refuses unsafe inputs it retains."""
        self.fx.collect_complete()
        with self.fx.qualify() as qualified:
            subject = qualified.subject
        self.fx.write_adjudication(subject)
        adjudication = self.fx.adjudication_path
        # A group/other-writable retained input is refused by the descriptor
        # qualification itself, before the owner read.
        os.chmod(adjudication, 0o606)
        try:
            with self.assertRaises(self.fx.collector.OriginalDeliveryRefused) as caught:
                self.fx.publish()
            self.assertEqual(caught.exception.reason,
                             "quality_retained_source_changed")
        finally:
            os.chmod(adjudication, 0o600)
        # A symlinked retained input is never followed.
        raw = adjudication.read_bytes()
        target = self.fx.base / "adjudication-target.json"
        exclusive(target, raw)
        adjudication.unlink()
        os.symlink(target, adjudication)
        try:
            with self.assertRaises(self.fx.collector.OriginalDeliveryRefused):
                self.fx.publish()
        finally:
            adjudication.unlink()
            exclusive(adjudication, raw)
            target.unlink()
        self.assertEqual(self.fx.record()["state"], "RECORDED")

    # ---- guarded closed readback -------------------------------------------

    def test_readback_guard_refuses_foreign_scope_with_zero_io(self):
        self.fx.collect_complete()
        self.fx.record()
        import artifact_delivery as delivery_module

        class NoSidecarIO:
            def __init__(self, *args, **kwargs):
                raise AssertionError("sidecar IO attempted before the scope guard")

        saved = delivery_module.DirectoryChain
        delivery_module.DirectoryChain = NoSidecarIO
        cases = [
            ({"CODEX_THREAD_ID": "child-thread-2"}, "quality_caller_not_original_root",
             RUN_ID, ROOT, PARENT),
            ({"CODEX_THREAD_ID": ROOT, "POOL_ORCHESTRATOR_ID": "coordinator-2"},
             "quality_caller_coordinator_label_mismatch", RUN_ID, ROOT, PARENT),
            ({"CODEX_THREAD_ID": ROOT, "POOL_ORCHESTRATOR_ID": ROOT,
              "POOL_PARENT_RUN_ID": "other-parent-2"},
             "quality_caller_parent_label_mismatch", RUN_ID, ROOT, PARENT),
            ({}, "quality_caller_not_original_root", RUN_ID, "foreign-root-1", PARENT),
        ]
        try:
            for extra, reason, run, root, parent in cases:
                self.set_env(**extra)
                with self.assertRaises(self.fx.collector.OriginalDeliveryRefused) as caught:
                    self.fx.ledger.read_collection_quality(run, root=root, parent=parent)
                self.assertEqual(caught.exception.reason, reason)
            # Malformed scope input is refused before any IO as well.
            self.set_env(CODEX_THREAD_ID=ROOT, POOL_ORCHESTRATOR_ID=None,
                         POOL_PARENT_RUN_ID=None)
            with self.assertRaises(self.fx.ledger.CollectionQualityRefused):
                self.fx.ledger.read_collection_quality(None, root=ROOT, parent=PARENT)
            with self.assertRaises(self.fx.ledger.CollectionQualityRefused):
                self.fx.ledger.read_collection_quality(RUN_ID, root=ROOT, parent="")
        finally:
            delivery_module.DirectoryChain = saved
            self.set_env(CODEX_THREAD_ID=ROOT, POOL_ORCHESTRATOR_ID=None,
                         POOL_PARENT_RUN_ID=None)
        # A claimed-but-unlabelled foreign parent requires the read and then
        # never projects the attested row as positive.
        projection = self.fx.ledger.read_collection_quality(RUN_ID, root=ROOT,
                                                            parent="foreign-parent-1")
        self.assertEqual(projection["state"], "UNQUALIFIED")
        self.assertEqual(projection["reason"], "collection_quality_scope_mismatch")
        # A foreign run has no row at all here.
        self.assertEqual(self.fx.ledger.read_collection_quality(
            "other-run-1", root=ROOT, parent=PARENT)["state"], "NOT_RECORDED")
        # The recorded row is untouched and still positive for the true scope.
        self.assertEqual(self.fx.inspect()["state"], "RECORDED")

    def test_readback_refuses_schema_only_unknown_tampered_rows(self):
        self.fx.collect_complete()
        outcome = self.fx.record()
        canonical_path = Path(outcome["path"])
        good = canonical_path.read_bytes()

        def rewrite(raw):
            canonical_path.unlink()
            exclusive(canonical_path, raw)

        def projection_state():
            return self.fx.inspect()

        def assert_unqualified(reason=None):
            projection = projection_state()
            self.assertEqual(projection["state"], "UNQUALIFIED")
            self.assertNotIn("collected_source_quality", projection)
            self.assertNotIn("attestation", projection)
            if reason is not None:
                self.assertEqual(projection["reason"], reason)
            rewrite(good)

        # Schema-only row.
        rewrite(canonical({"schema": QUALITY_SCHEMA, "run_id": RUN_ID}) + b"\n")
        assert_unqualified("collection_quality_attestation_invalid")
        # Unknown field (an acceptance field must never ride along).
        row = json.loads(good)
        row["accepted_by"] = "deterministic"
        rewrite(canonical(row) + b"\n")
        assert_unqualified("collection_quality_attestation_invalid")
        # Tampered verdict projection without the adjudication behind it.
        row = json.loads(good)
        row["collected_source_quality"] = "FAIL"
        rewrite(canonical(row) + b"\n")
        assert_unqualified("collection_quality_adjudication_crossbinding_invalid")
        # Tampered adjudication digest.
        row = json.loads(good)
        row["adjudication"]["adjudication_sha256"] = "0" * 64
        rewrite(canonical(row) + b"\n")
        assert_unqualified("collection_quality_adjudication_digest_mismatch")
        # Altered subject digest inside the attested source section.
        row = json.loads(good)
        row["source"]["packet_sha256"] = "1" * 64
        rewrite(canonical(row) + b"\n")
        assert_unqualified("collection_quality_subject_diverged")
        # A claimed different parent scope never projects a positive: the row
        # is internally consistent but attests a different parent.
        row = json.loads(good)
        record_dict = dict(json.loads(row["adjudication"]["record"]),
                           parent="other-parent-3")
        record_bytes = canonical(record_dict)
        foreign = dict(row, parent="other-parent-3")
        foreign["adjudication"] = {"verdict": record_dict["verdict"],
                                   "by": record_dict["by"],
                                   "adjudication_sha256": sha(record_bytes),
                                   "record": record_bytes.decode()}
        rewrite(canonical(foreign) + b"\n")
        projection = self.fx.inspect()
        self.assertEqual(projection["state"], "UNQUALIFIED")
        self.assertEqual(projection["reason"], "collection_quality_scope_mismatch")
        rewrite(good)
        # Unreadable canonical bytes.
        rewrite(b"")
        self.assertEqual(projection_state()["state"], "CANONICAL_UNREADABLE")
        rewrite(good)
        self.assertEqual(projection_state()["state"], "RECORDED")

    def test_readback_missing_source_is_unqualified_not_positive(self):
        self.fx.collect_complete()
        self.fx.record()
        collection_backup = self.fx.base / "collection-backup"
        shutil.copytree(self.fx.destination, collection_backup)
        try:
            # Missing collection evidence.
            shutil.rmtree(self.fx.destination)
            projection = self.fx.inspect()
            self.assertEqual(projection["state"], "UNQUALIFIED")
            self.assertEqual(projection["reason"],
                             "collection_quality_evidence_quality_receipt_unreadable")
            self.assertNotIn("collected_source_quality", projection)
        finally:
            shutil.copytree(collection_backup, self.fx.destination)
            shutil.rmtree(collection_backup, ignore_errors=True)
        self.assertEqual(self.fx.inspect()["state"], "RECORDED")
        # The caller's binding path is a publication input, not a readback
        # dependency: the attestation stands on the collection's own verified
        # binding copy, so losing the publication input neither fabricates a
        # positive nor a refusal by itself.
        binding_backup = self.fx.binding_path.read_bytes()
        self.fx.binding_path.unlink()
        self.assertEqual(self.fx.inspect()["state"], "RECORDED")
        exclusive(self.fx.binding_path, binding_backup)
        # Tampering with that verified copy does refuse: the receipt binds its
        # exact digest and the copy must still reprove the same operation.
        copy = self.fx.destination / "binding.json"
        tampered = copy.read_bytes()
        copy.unlink()
        exclusive(copy, tampered.replace(b'"inert-host"', b'"inert-host-x"'))
        projection = self.fx.inspect()
        self.assertEqual(projection["state"], "UNQUALIFIED")
        self.assertEqual(projection["reason"],
                         "collection_quality_evidence_"
                         "quality_collection_readback_unqualified")
        self.assertNotIn("collected_source_quality", projection)
        copy.unlink()
        exclusive(copy, tampered)
        self.assertEqual(self.fx.inspect()["state"], "RECORDED")

    def test_cross_collection_runs_are_independent(self):
        first = self.fx.collect_complete()
        self.assertEqual(first["state"], "COMPLETE")
        outcome = self.fx.record()
        self.assertEqual(outcome["state"], "RECORDED")
        sidecar = Path(outcome["path"])
        before = sidecar.read_bytes()
        ledger_before = self.fx.ledger_bytes()
        with fixture_stack("collection-quality-second-") as fx:
            fx.collect_complete()
            outcome = fx.record()
            self.assertEqual(outcome["state"], "RECORDED")
            self.assertEqual(fx.inspect()["state"], "RECORDED")
        # A second install's publication never touched this owner's sidecar,
        # ledger or attestation bytes.
        self.assertEqual(self.fx.inspect()["state"], "RECORDED")
        self.assertEqual(sidecar.read_bytes(), before)
        self.assertEqual(self.fx.ledger_bytes(), ledger_before)

    def test_external_binding_path_publishes_readbacks_and_assesses(self):
        """A legitimate external binding composes end to end with no state copy.

        The owner publication accepts the caller's retained binding wherever it
        actually lives; the readback re-qualifies through the collection's own
        verified binding copy, so no <run>.binding.json in the owner state
        directory is required, created or written back, and no canonical source
        is mutated by any of the three compositions.
        """
        fx = self.fx
        external_dir = fx.base / "external-binding"
        external_dir.mkdir(mode=0o700)
        external = external_dir / f"{RUN_ID}.binding.json"
        exclusive(external, fx.binding_path.read_bytes())
        state_binding = fx.ctl / "state" / "remote_sub" / f"{RUN_ID}.binding.json"
        state_binding.unlink()
        fx.binding_path = external
        self.assertFalse(state_binding.exists())
        state = fx.ctl / "state" / "remote_sub"
        sidecar_suffixes = (".collection-quality.json", ".collection-quality.pending.json")
        source_names = sorted(item.name for item in state.iterdir()
                              if not item.name.endswith(sidecar_suffixes))
        self.assertIn(f"{RUN_ID}.log", source_names)

        def sources():
            return {name: (sha((state / name).read_bytes()),
                           os.stat(state / name).st_ino)
                    for name in source_names}

        fx.collect_complete()
        before = sources()
        outcome = fx.record()
        self.assertEqual(outcome["state"], "RECORDED")
        self.assertFalse(outcome["idempotent"])
        projection = fx.inspect()
        self.assertEqual(projection["state"], "RECORDED")
        self.assertEqual(projection["collected_source_quality"], "PASS")
        # Neither publication nor inspection created the state binding copy or
        # touched any canonical retained source.
        self.assertFalse(state_binding.exists())
        self.assertEqual(sources(), before)
        # The whole assessment composes on the external binding path too.
        self.assertIs(fx.publish_terminal_row(), True)
        fx.write_controller_proof()
        fx.write_broker()
        dimensions = fx.fabric.assess_settlement(
            RUN_ID, root=ROOT, parent=PARENT)["dimensions"]
        self.assertEqual(dimensions["project_delivery"]["state"], "VERIFIED")
        self.assertEqual(dimensions["quality_recorded"]["state"], "RECORDED")
        self.assertEqual(dimensions["terminal_publication"]["state"], "VERIFIED")
        self.assertEqual(dimensions["controller_return"]["state"], "VERIFIED")
        self.assertEqual(dimensions["broker_lease"]["state"], "VERIFIED")
        self.assertFalse(state_binding.exists())
        self.assertEqual(sources(), before)


class OldOwnerCompatibilityCase(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in
                       ("CODEX_THREAD_ID", "POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID",
                        "POOL_LEDGER_PATH", "INERT_HOME", "INERT_ARTIFACT_ROOT", "PATH")}
        self._stack = stack("collection-quality-old-")
        self.fx = Fixture(self._stack)
        os.environ["CODEX_THREAD_ID"] = ROOT
        os.environ.pop("POOL_ORCHESTRATOR_ID", None)
        os.environ.pop("POOL_PARENT_RUN_ID", None)
        os.environ["POOL_LEDGER_PATH"] = str(self.fx.ledger_path)
        self.fx.ledger.LEDGER_PATH = str(self.fx.ledger_path)
        self.fx.ledger.LEDGER_DIR = str(self.fx.base)
        self.old = load_old_ledger(SRC / "pool_ledger.py", "old")
        self.old.LEDGER_PATH = str(self.fx.ledger_path)
        self.old.LEDGER_DIR = str(self.fx.base)

    def tearDown(self):
        if getattr(self, "fx", None) is not None:
            self.fx.cleanup()
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._stack.cleanup()

    def test_old_owner_semantics_identical_and_sidecar_publication_is_invisible(self):
        self.fx.collect_complete()
        records = [{"ts": 1, "pool": "glm", "key": "-", "window_id": "w", "task_class": "t",
                    "rc": 0, "tokens": 5, "signal": "ok", "run_id": RUN_ID,
                    "accepted_by": "deterministic", "review_rejected": False,
                    "scope_violation": False, "retries": 0, "escalated": False,
                    "wall_s": 1.0, "model": MODEL, "input_tokens": 1, "cached_tokens": 0,
                    "output_tokens": 4, "credits": None, "credit_rate": None}]
        self.assertEqual(self.old.merge_jobs(records), self.fx.ledger.merge_jobs(records))
        self.assertEqual(self.old.compute_stats(records), self.fx.ledger.compute_stats(records))
        # The old owner publishes the original run's terminal row first.
        self.assertIs(self.fx.publish_terminal_row(ledger=self.old), True)
        before = self.fx.ledger_bytes()
        self.assertEqual(self.old.read_acceptance(RUN_ID, expected_rc=0, expected_signal="ok"),
                         self.fx.ledger.read_acceptance(RUN_ID, expected_rc=0,
                                                        expected_signal="ok"))
        # Sidecar publication and inspection leave the canonical ledger bytes
        # and the old owner's read view exactly unchanged.
        self.fx.record()
        self.fx.inspect()
        self.assertEqual(self.fx.ledger_bytes(), before)
        self.assertEqual(self.old.read_acceptance(RUN_ID, expected_rc=0, expected_signal="ok"),
                         {"accepted": False, "accepted_by": None,
                          "acceptance_state": "NOT_ACCEPTED",
                          "acceptance_reason": "NO_OUTCOME",
                          "root_id": ROOT, "parent_run_id": PARENT})

    def test_old_strict_terminal_writer_then_old_normal_accept_after_sidecar(self):
        self.fx.collect_complete()
        self.fx.record()
        before = self.fx.ledger_bytes()
        # The retained OLD strict terminal writer publishes the same original
        # run after the sidecar: no orphan outcome and no conflicting terminal.
        self.assertIs(self.fx.publish_terminal_row(ledger=self.old), True)
        self.assertNotEqual(self.fx.ledger_bytes(), before)
        identity = self.old.read_execution_identity(RUN_ID, expected_rc=0, expected_signal="ok")
        self.assertEqual(identity["lineage_state"], "VERIFIED_TERMINAL")
        self.assertEqual(identity["root_id"], ROOT)
        self.assertEqual(identity["parent_run_id"], PARENT)
        self.assertIs(self.old.record_outcome(RUN_ID, accepted_by="deterministic",
                                              strict=True), True)
        acceptance = self.old.read_acceptance(RUN_ID, expected_rc=0, expected_signal="ok")
        self.assertEqual(acceptance["acceptance_state"], "ACCEPTED")
        self.assertEqual(acceptance["accepted_by"], "deterministic")
        # The candidate overlay reads the identical projection from the same file.
        self.assertEqual(self.fx.ledger.read_acceptance(RUN_ID, expected_rc=0,
                                                        expected_signal="ok"), acceptance)
        # The quality attestation is untouched by ledger lifecycle traffic.
        self.assertEqual(self.fx.inspect()["state"], "RECORDED")


class SettlementCase(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in
                       ("CODEX_THREAD_ID", "POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID",
                        "POOL_LEDGER_PATH", "INERT_HOME", "INERT_ARTIFACT_ROOT", "PATH")}
        self._stack = stack("collection-quality-settle-")
        self.fx = Fixture(self._stack)
        os.environ["CODEX_THREAD_ID"] = ROOT
        os.environ.pop("POOL_ORCHESTRATOR_ID", None)
        os.environ.pop("POOL_PARENT_RUN_ID", None)
        os.environ["POOL_LEDGER_PATH"] = str(self.fx.ledger_path)
        self.fx.ledger.LEDGER_PATH = str(self.fx.ledger_path)
        self.fx.ledger.LEDGER_DIR = str(self.fx.base)

    def tearDown(self):
        if getattr(self, "fx", None) is not None:
            self.fx.cleanup()
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._stack.cleanup()

    def settled_fixture(self, *, verdict="PASS", expired=False, controller_rc=0,
                        prelease=None, mode="body", with_terminal=True):
        self.fx.collect_complete()
        self.fx.record(verdict=verdict)
        if with_terminal:
            self.assertIs(self.fx.publish_terminal_row(), True)
        self.fx.write_controller_proof(controller_rc=controller_rc, prelease=prelease,
                                       mode=mode)
        self.fx.write_broker(state="expired" if expired else "released")
        return self.fx

    def assess(self):
        return self.fx.fabric.assess_settlement(RUN_ID, root=ROOT, parent=PARENT)

    def test_every_dimension_can_verify_but_host_lane_keeps_aggregate_unknown(self):
        fx = self.settled_fixture()
        assessment = self.assess()
        dimensions = assessment["dimensions"]
        self.assertEqual(dimensions["project_delivery"]["state"], "VERIFIED")
        self.assertEqual(dimensions["worker_terminal"]["state"], "VERIFIED")
        self.assertEqual(dimensions["quality_recorded"]["state"], "RECORDED")
        self.assertEqual(dimensions["quality_recorded"]["verdict"], "PASS")
        self.assertEqual(dimensions["terminal_publication"]["state"], "VERIFIED")
        self.assertEqual(dimensions["controller_return"]["state"], "VERIFIED")
        self.assertEqual(dimensions["controller_return"]["controller_rc"], 0)
        self.assertEqual(dimensions["broker_lease"]["state"], "VERIFIED")
        self.assertEqual(dimensions["broker_lease"]["lease_state"], "released")
        self.assertEqual(dimensions["host_lane"]["state"], "UNKNOWN")
        self.assertIn("no durable normal-release proof",
                      dimensions["host_lane"]["capability_boundary"])
        self.assertEqual(assessment["aggregate"]["state"], "UNKNOWN")
        self.assertEqual(assessment["aggregate"]["missing"], ["host_lane"])
        self.assertTrue(assessment["assessment_only"])
        self.assertEqual(assessment["mutation"], "none")
        self.assertFalse(assessment["acceptance_granted"])
        self.assertFalse(assessment["retry_authorized"])
        self.assertEqual(assessment["controller_process_jsonl"]["state"],
                         "NOT_USABLE_AS_CONTROLLER_EXIT")

    def test_controller_return_binds_original_caller_text_to_transported_packet(self):
        self.fx.collect_complete()
        self.fx.record()
        subject = self.fx.attested_subject()
        # The production-true shape: the retained request packet is the
        # ORIGINAL caller text, i.e. the bytes before the producer appended its
        # deterministic delivery instructions and wrapped the envelope.
        self.fx.write_controller_proof(mode="body")
        dimension = self.fx.fabric._retained_request_return(
            RUN_ID, ROOT, PARENT, subject=subject)
        self.assertEqual(dimension["state"], "VERIFIED")
        self.assertEqual(dimension["packet_sha256"], sha(self.fx.body))
        # The reproduced producer encoding is exactly the transported packet
        # the qualified original binding pinned.
        self.assertEqual(dimension["transport_packet_sha256"], sha(self.fx.packet))
        self.assertNotEqual(dimension["packet_sha256"],
                            self.fx.contract["body_sha256"])
        self.assertNotEqual(dimension["packet_sha256"], sha(self.fx.packet))
        # A retained request packet that is itself the wrapped artifact request
        # is not the original caller text: it proves no producer relation.
        self.fx.write_controller_proof(mode="artifact")
        dimension = self.fx.fabric._retained_request_return(
            RUN_ID, ROOT, PARENT, subject=subject)
        self.assertEqual(dimension["state"], "UNKNOWN")
        self.assertEqual(dimension["reason"],
                         "controller_packet_not_original_caller_text")

    def test_controller_return_producer_relation_negatives(self):
        self.fx.collect_complete()
        self.fx.record()
        subject = self.fx.attested_subject()
        state = self.fx.ctl / "state" / "remote_sub"

        def rewrite(packet_bytes, **row_changes):
            """Retain one internally consistent proof bundle over new bytes."""
            proof = self.fx.write_controller_proof()
            request_row = json.loads(proof["request"])
            launch_row = json.loads(proof["launch"])
            returned = json.loads(proof["return"])
            request_row["packet_sha256"] = sha(packet_bytes)
            request_row["packet_bytes"] = len(packet_bytes)
            launch_row["packet_sha256"] = sha(packet_bytes)
            request_row.update(row_changes.get("request", {}))
            launch_row.update(row_changes.get("launch", {}))
            request_raw = canonical(request_row)
            # The launch row binds the exact retained request row bytes.
            launch_row["request_sha256"] = sha(request_raw)
            launch_raw = canonical(launch_row)
            returned["request_sha256"] = sha(request_raw)
            returned["launch_sha256"] = sha(launch_raw)
            for name, raw in ((f"{RUN_ID}.request.packet", packet_bytes),
                              (f"{RUN_ID}.request.json", request_raw),
                              (f"{RUN_ID}.request-launch.json", launch_raw),
                              (f"{RUN_ID}.request-return.json", canonical(returned))):
                target = state / name
                target.unlink()
                exclusive(target, raw)

        # A changed original caller text reproduces a different transported
        # packet, so the qualified collection is not this controller's run.
        changed = self.fx.body + b"changed\n"
        rewrite(changed)
        dimension = self.fx.fabric._retained_request_return(
            RUN_ID, ROOT, PARENT, subject=subject)
        self.assertEqual(dimension["state"], "UNKNOWN")
        self.assertEqual(dimension["reason"],
                         "controller_packet_producer_relation_unproven")
        self.assertEqual(dimension["caller_packet_sha256"], sha(changed))
        self.assertEqual(dimension["transport_packet_sha256"], sha(self.fx.packet))
        # A subject whose support generation is not the one this run's own
        # binding pinned is a different collection: no equivalence is invented.
        rewrite(self.fx.body)
        other = dict(subject, support_digest="f" * 64)
        dimension = self.fx.fabric._retained_request_return(
            RUN_ID, ROOT, PARENT, subject=other)
        self.assertEqual(dimension["state"], "UNKNOWN")
        self.assertEqual(dimension["reason"],
                         "controller_packet_producer_relation_unproven")
        # A subject whose pinned packet digest is not the reproduced encoding.
        other = dict(subject, packet_sha256="0" * 64)
        dimension = self.fx.fabric._retained_request_return(
            RUN_ID, ROOT, PARENT, subject=other)
        self.assertEqual(dimension["state"], "UNKNOWN")
        self.assertEqual(dimension["reason"],
                         "controller_packet_producer_relation_unproven")
        # Without a qualified collected artifact subject the proof cannot be
        # bound to anything at all.
        dimension = self.fx.fabric._retained_request_return(RUN_ID, ROOT, PARENT)
        self.assertEqual(dimension["state"], "UNKNOWN")
        self.assertEqual(dimension["reason"],
                         "collected_artifact_subject_unavailable")

    def test_controller_return_negatives_refuse_positive(self):
        fx = self.settled_fixture()
        state = fx.ctl / "state" / "remote_sub"
        subject = fx.attested_subject()
        expected = fx.fabric._retained_request_return(RUN_ID, ROOT, PARENT,
                                                      subject=subject)
        self.assertEqual(expected["state"], "VERIFIED")
        (state / f"{RUN_ID}.request-return.json").unlink()
        self.assertEqual(fx.fabric._retained_request_return(
            RUN_ID, ROOT, PARENT, subject=subject)["reason"], "request_return_absent")
        fx.write_controller_proof(controller_rc=3)
        self.assertEqual(fx.fabric._retained_request_return(
            RUN_ID, ROOT, PARENT, subject=subject)["reason"],
            "controller_return_nonzero")
        fx.write_controller_proof(prelease="a" * 64)
        self.assertEqual(fx.fabric._retained_request_return(
            RUN_ID, ROOT, PARENT, subject=subject)["reason"],
            "prelease_failure_bound")
        fx.write_controller_proof(root="other-root-1")
        self.assertEqual(fx.fabric._retained_request_return(
            RUN_ID, ROOT, PARENT, subject=subject)["reason"],
            "request_return_not_current_native_return")
        fx.write_controller_proof()
        (state / f"{RUN_ID}.request.json").unlink()
        self.assertEqual(fx.fabric._retained_request_return(
            RUN_ID, ROOT, PARENT, subject=subject)["reason"],
            "controller_proof_artifact_missing")
        fx.write_controller_proof()
        log = fx.log_path.read_bytes()
        fx.log_path.unlink()
        exclusive(fx.log_path, log + (fx.log_head("2026-10-20T00:02Z")
                                      + "POLL 1/60 elapsed=1 file=x\n").encode())
        self.assertEqual(fx.fabric._retained_request_return(
            RUN_ID, ROOT, PARENT, subject=subject)["reason"],
            "controller_return_digest_mismatch")
        # A returned-but-artifact packet whose contract scope disagrees refuses.
        fx.log_path.unlink()
        exclusive(fx.log_path, log)
        fx.write_controller_proof(mode="artifact")
        raw = json.loads((state / f"{RUN_ID}.request-return.json").read_bytes())
        raw["request_sha256"] = "0" * 64
        target = state / f"{RUN_ID}.request-return.json"
        target.unlink()
        exclusive(target, canonical(raw))
        self.assertEqual(fx.fabric._retained_request_return(
            RUN_ID, ROOT, PARENT, subject=subject)["reason"],
            "controller_return_digest_mismatch")

    def test_terminal_publication_with_failed_controller_exit_is_not_settled(self):
        fx = self.settled_fixture(controller_rc=3)
        assessment = self.assess()
        dimensions = assessment["dimensions"]
        self.assertEqual(dimensions["terminal_publication"]["state"], "VERIFIED")
        self.assertEqual(dimensions["controller_return"]["state"], "UNKNOWN")
        self.assertEqual(dimensions["controller_return"]["reason"], "controller_return_nonzero")
        self.assertNotEqual(assessment["aggregate"]["state"], "SETTLED")
        self.assertIn("controller_return", assessment["aggregate"]["missing"])

    def test_released_broker_lease_positive_and_negatives(self):
        fx = self.settled_fixture()
        self.assertEqual(self.assess()["dimensions"]["broker_lease"]["state"], "VERIFIED")
        # Expired is never released.
        fx.write_broker(state="expired")
        dimension = self.assess()["dimensions"]["broker_lease"]
        self.assertEqual(dimension["state"], "UNKNOWN")
        self.assertEqual(dimension["reason"], "released_lease_not_proven")
        # A mismatched row is not the released lease.
        fx.write_broker(account="other-account")
        dimension = self.assess()["dimensions"]["broker_lease"]
        self.assertEqual(dimension["state"], "UNKNOWN")
        self.assertEqual(dimension["reason"], "released_lease_not_proven")
        # No broker snapshot at all.
        (fx.ctl / "broker" / "leases.sqlite").unlink()
        self.assertEqual(self.assess()["dimensions"]["broker_lease"]["reason"],
                         "broker_snapshot_absent")
        # A missing genuine acquire binding leaves the dimension UNKNOWN even
        # when a caller asserts a lease label.
        log = fx.log_path.read_bytes()
        head = fx.log_head("2026-10-20T00:03Z")
        filtered = b"".join(line + b"\n" for line in log.splitlines()
                            if not line.startswith(b"") or b"LAUNCH_BINDING" not in line)
        fx.log_path.unlink()
        exclusive(fx.log_path, filtered)
        binding = fx.fabric._retained_launch_binding_record(RUN_ID, ROOT, PARENT)
        self.assertIsNone(binding)
        dimension = self.assess()["dimensions"]["broker_lease"]
        self.assertEqual(dimension["state"], "UNKNOWN")
        self.assertEqual(dimension["reason"], "retained_acquire_binding_missing")

    def test_released_lease_must_match_the_qualified_collection(self):
        """A released broker row settles only its own qualified collection.

        The collection here is genuinely qualified for a different requested
        model than the retained acquire record and the released broker snapshot
        carry, so the record and the snapshot agree with each other and only
        the qualified-subject binding can refuse the positive.
        """
        with fixture_stack("collection-quality-broker-", binding_model="other-model") as fx:
            fx.collect_complete()
            fx.record()
            subject = fx.attested_subject()
            self.assertEqual(subject["requested_model"], "other-model")
            self.assertIs(fx.publish_terminal_row(), True)
            fx.write_controller_proof()
            fx.write_broker()
            assessment = fx.fabric.assess_settlement(RUN_ID, root=ROOT, parent=PARENT)
            result = assessment["dimensions"]["broker_lease"]
            self.assertEqual(result["state"], "UNKNOWN")
            self.assertEqual(result["reason"], "released_lease_subject_mismatch")
            self.assertEqual(result["mismatched"], ["requested_model"])
            self.assertNotEqual(assessment["aggregate"]["state"], "SETTLED")
            # The same subject is what the owner dimension is handed, so every
            # other component diverges exactly the same way: a released row for
            # a foreign host, packet or support generation is not this
            # collection's release either.
            binding = fx.fabric._retained_launch_binding_record(RUN_ID, ROOT, PARENT)
            self.assertIsNotNone(binding)
            for field, value in (("host", "other-host"), ("mode", "qwen"),
                                 ("packet_sha256", "f" * 64),
                                 ("support_digest", "f" * 64),
                                 ("root", "other-root-3"), ("parent", "other-parent-6"),
                                 ("run_id", "other-run-3")):
                result = fx.fabric._broker_lease_dimension(
                    RUN_ID, binding, dict(subject, **{field: value}))
                self.assertEqual(result["state"], "UNKNOWN", field)
                self.assertEqual(result["reason"], "released_lease_subject_mismatch",
                                 field)
                # This fixture's model divergence is intentionally present in
                # every case; the diverged field must always be reported too.
                self.assertIn(field, result["mismatched"], field)
        # The matching collection verifies end to end, and a released snapshot
        # for a different lease than the retained acquire record never proves
        # this run's release.
        self.settled_fixture()
        self.assertEqual(self.assess()["dimensions"]["broker_lease"]["state"],
                         "VERIFIED")
        self.fx.write_broker(lease_id="ffffffffffff")
        self.assertEqual(
            self.assess()["dimensions"]["broker_lease"],
            {"state": "UNKNOWN", "reason": "released_lease_not_proven",
             "lease_id": LEASE_ID})
        self.fx.write_broker()
        self.assertEqual(self.assess()["dimensions"]["broker_lease"]["state"],
                         "VERIFIED")

    def test_assessment_enforces_caller_guard_before_any_io(self):
        """A child or foreign scope is refused before the assessment reads."""
        self.fx.collect_complete()
        self.fx.record()
        import artifact_delivery as delivery_module

        class NoIO:
            def __init__(self, *args, **kwargs):
                raise AssertionError("assessment IO before the caller guard")

        def no_read(*args, **kwargs):
            raise AssertionError("assessment IO before the caller guard")

        saved_chain = delivery_module.DirectoryChain
        saved_read = delivery_module.read_local_at
        cases = [
            ({"CODEX_THREAD_ID": "child-thread-3"}, "quality_caller_not_original_root"),
            ({"CODEX_THREAD_ID": ROOT, "POOL_ORCHESTRATOR_ID": "coordinator-3"},
             "quality_caller_coordinator_label_mismatch"),
            ({"CODEX_THREAD_ID": ROOT, "POOL_ORCHESTRATOR_ID": ROOT,
              "POOL_PARENT_RUN_ID": "other-parent-4"},
             "quality_caller_parent_label_mismatch"),
        ]
        try:
            delivery_module.DirectoryChain = NoIO
            delivery_module.read_local_at = no_read
            for extra, reason in cases:
                os.environ.update(extra)
                with self.assertRaises(self.fx.collector.OriginalDeliveryRefused) as caught:
                    self.fx.fabric.assess_settlement(RUN_ID, root=ROOT, parent=PARENT)
                self.assertEqual(caught.exception.reason, reason)
            # A foreign claimed root is refused at zero IO as well: the whole
            # assessment is guarded, not only the quality readback.
            os.environ["CODEX_THREAD_ID"] = ROOT
            os.environ.pop("POOL_ORCHESTRATOR_ID", None)
            os.environ.pop("POOL_PARENT_RUN_ID", None)
            with self.assertRaises(self.fx.collector.OriginalDeliveryRefused) as caught:
                self.fx.fabric.assess_settlement(RUN_ID, root="foreign-root-2",
                                                 parent=PARENT)
            self.assertEqual(caught.exception.reason, "quality_caller_not_original_root")
        finally:
            delivery_module.DirectoryChain = saved_chain
            delivery_module.read_local_at = saved_read
            os.environ["CODEX_THREAD_ID"] = ROOT
            os.environ.pop("POOL_ORCHESTRATOR_ID", None)
            os.environ.pop("POOL_PARENT_RUN_ID", None)
        # The same caller composes the full assessment afterwards.
        self.fx.write_controller_proof()
        assessment = self.assess()
        self.assertEqual(assessment["dimensions"]["quality_recorded"]["state"],
                         "RECORDED")
        self.assertEqual(assessment["dimensions"]["controller_return"]["state"],
                         "VERIFIED")

    def test_unsafe_controller_proofs_and_directory_are_never_a_positive(self):
        """The inert world-writable repro refuses under strict owner custody."""
        fx = self.settled_fixture()
        state = fx.ctl / "state" / "remote_sub"
        # The retained proof bundle world-writable, exactly like the repro: the
        # request/launch/return rows and the retained caller packet are proof
        # files the strict owner read refuses, and none of them is a quality
        # input, so the qualified subject stays available.
        proofs = [f"{RUN_ID}.request-return.json", f"{RUN_ID}.request.json",
                  f"{RUN_ID}.request-launch.json", f"{RUN_ID}.request.packet"]
        for name in proofs:
            os.chmod(state / name, 0o666)
        try:
            assessment = self.assess()
        finally:
            for name in proofs:
                os.chmod(state / name, 0o600)
        dimension = assessment["dimensions"]["controller_return"]
        self.assertEqual(dimension["state"], "UNKNOWN")
        self.assertEqual(dimension["reason"], "controller_proof_artifact_unreadable")
        self.assertNotEqual(assessment["aggregate"]["state"], "SETTLED")
        # With the retained controller log world-writable as well, no positive
        # survives: the same unsafe file is a quality input, so the qualified
        # subject itself is gone and the proof can bind to nothing.
        os.chmod(state / f"{RUN_ID}.log", 0o666)
        try:
            assessment = self.assess()
        finally:
            os.chmod(state / f"{RUN_ID}.log", 0o600)
        dimension = assessment["dimensions"]["controller_return"]
        self.assertEqual(dimension["state"], "UNKNOWN")
        self.assertIn(dimension["reason"],
                      ("collected_artifact_subject_unavailable",
                       "controller_proof_artifact_unreadable"))
        self.assertNotEqual(assessment["aggregate"]["state"], "SETTLED")
        # An unsafe retained-proof directory refuses with its own reason. The
        # same directory also holds the quality sidecar owner, so the isolated
        # reason is proven through the owner helper on a held subject.
        subject = fx.attested_subject()
        os.chmod(state, 0o703)
        try:
            dimension = fx.fabric._retained_request_return(
                RUN_ID, ROOT, PARENT, subject=subject)
        finally:
            os.chmod(state, 0o700)
        self.assertEqual(dimension["state"], "UNKNOWN")
        self.assertEqual(dimension["reason"], "controller_proof_directory_unsafe")
        # The restored custody composes the positive again.
        self.assertEqual(self.assess()["dimensions"]["controller_return"]["state"],
                         "VERIFIED")

    def test_same_bytes_proof_replacement_during_assessment_refuses(self):
        fx = self.settled_fixture()
        state = fx.ctl / "state" / "remote_sub"
        target = state / f"{RUN_ID}.request.json"
        raw = target.read_bytes()
        saved = self.fx.race_on_owner_read(f"{RUN_ID}.request.json",
                                           lambda: (target.unlink(),
                                                    exclusive(target, raw)))
        try:
            assessment = self.assess()
        finally:
            self.fx.restore_owner_read(saved)
        dimension = assessment["dimensions"]["controller_return"]
        self.assertEqual(dimension["state"], "UNKNOWN")
        self.assertEqual(dimension["reason"],
                         "controller_proof_replaced_during_assessment")
        self.assertNotEqual(assessment["aggregate"]["state"], "SETTLED")
        # The unchanged proof bundle verifies again.
        self.assertEqual(self.assess()["dimensions"]["controller_return"]["state"],
                         "VERIFIED")

    def test_quality_pass_with_expired_lease_is_not_settled(self):
        fx = self.settled_fixture(expired=True)
        assessment = self.assess()
        self.assertEqual(assessment["dimensions"]["quality_recorded"]["verdict"], "PASS")
        self.assertEqual(assessment["dimensions"]["broker_lease"]["state"], "UNKNOWN")
        self.assertEqual(assessment["aggregate"]["state"], "UNKNOWN")
        self.assertIn("broker_lease", assessment["aggregate"]["missing"])

    def test_unrecorded_quality_keeps_delivery_unknown(self):
        self.fx.collect_complete()
        self.fx.write_controller_proof()
        self.fx.write_broker()
        assessment = self.assess()
        dimensions = assessment["dimensions"]
        self.assertEqual(dimensions["project_delivery"]["state"], "UNKNOWN")
        self.assertEqual(dimensions["project_delivery"]["reason"],
                         "quality_attestation_not_recorded")
        self.assertEqual(dimensions["worker_terminal"]["state"], "UNKNOWN")
        self.assertEqual(dimensions["quality_recorded"]["state"], "NOT_RECORDED")
        self.assertIsNone(dimensions["quality_recorded"]["verdict"])
        self.assertEqual(assessment["aggregate"]["state"], "UNKNOWN")

    def test_unqualified_quality_keeps_every_dimension_unpositive(self):
        fx = self.settled_fixture()
        self.assertEqual(self.assess()["dimensions"]["quality_recorded"]["state"],
                         "RECORDED")
        # Removing the retained collection makes the attestation unprovable:
        # no delivery, worker or quality positive may survive.
        backup = fx.base / "settle-collection-backup"
        shutil.copytree(fx.destination, backup)
        shutil.rmtree(fx.destination)
        try:
            assessment = self.assess()
        finally:
            shutil.copytree(backup, fx.destination)
            shutil.rmtree(backup, ignore_errors=True)
        dimensions = assessment["dimensions"]
        self.assertEqual(dimensions["quality_recorded"]["state"], "UNQUALIFIED")
        self.assertIsNone(dimensions["quality_recorded"]["verdict"])
        self.assertEqual(dimensions["project_delivery"]["state"], "UNKNOWN")
        self.assertEqual(dimensions["worker_terminal"]["state"], "UNKNOWN")
        self.assertEqual(assessment["aggregate"]["state"], "UNKNOWN")
        self.assertIn("quality_recorded", assessment["aggregate"]["missing"])
        # Recovery is observed, not manufactured: the evidence is back.
        self.assertEqual(self.assess()["dimensions"]["quality_recorded"]["state"],
                         "RECORDED")


class CliCompositionCase(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in
                       ("CODEX_THREAD_ID", "POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID",
                        "POOL_LEDGER_PATH", "INERT_HOME", "INERT_ARTIFACT_ROOT", "PATH")}
        self._stack = stack("collection-quality-cli-")
        self.fx = Fixture(self._stack)

    def tearDown(self):
        if getattr(self, "fx", None) is not None:
            self.fx.cleanup()
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._stack.cleanup()

    def prepare_adjudication(self, verdict="PASS"):
        with self.fx.qualify() as qualified:
            subject = qualified.subject
        self.fx.write_adjudication(subject, verdict=verdict)
        return subject

    def test_cli_quality_record_inspect_settlement_end_to_end(self):
        self.fx.collect_complete()
        self.prepare_adjudication()
        env = {"POOL_LEDGER_PATH": str(self.fx.ledger_path)}
        recorded = self.fx.cli("quality-record", RUN_ID, "--root", ROOT, "--parent", PARENT,
                               "--binding", str(self.fx.binding_path),
                               "--collection", str(self.fx.destination / "receipt.json"),
                               "--receipt-sha256", sha(self.fx.receipt_raw()),
                               "--adjudication", str(self.fx.adjudication_path), **env)
        self.assertEqual(recorded.returncode, 0, recorded.stderr)
        outcome = json.loads(recorded.stdout)
        self.assertEqual(outcome["state"], "RECORDED")
        self.assertEqual(outcome["collected_source_quality"], "PASS")
        inspected = self.fx.cli("quality-inspect", RUN_ID, "--root", ROOT,
                                "--parent", PARENT, **env)
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        projection = json.loads(inspected.stdout)
        self.assertEqual(projection["state"], "RECORDED")
        self.assertTrue(projection["caller_scope_matches"])
        # The CLI composes the same owner: a repeat record is idempotent.
        repeat = self.fx.cli("quality-record", RUN_ID, "--root", ROOT, "--parent", PARENT,
                             "--binding", str(self.fx.binding_path),
                             "--collection", str(self.fx.destination / "receipt.json"),
                             "--receipt-sha256", sha(self.fx.receipt_raw()),
                             "--adjudication", str(self.fx.adjudication_path), **env)
        self.assertEqual(repeat.returncode, 0, repeat.stderr)
        self.assertTrue(json.loads(repeat.stdout)["idempotent"])
        # Full settlement composition with every retained proof.
        self.assertIs(self.fx.publish_terminal_row(), True)
        self.assertEqual(self.fx.ledger_bytes() != b"", True)
        self.fx.write_controller_proof()
        self.fx.write_broker()
        settled = self.fx.cli("settlement-assessment", RUN_ID, "--root", ROOT,
                              "--parent", PARENT, **env)
        self.assertEqual(settled.returncode, 0, settled.stderr)
        assessment = json.loads(settled.stdout)
        self.assertEqual(assessment["dimensions"]["project_delivery"]["state"], "VERIFIED")
        self.assertEqual(assessment["dimensions"]["terminal_publication"]["state"], "VERIFIED")
        self.assertEqual(assessment["dimensions"]["controller_return"]["state"], "VERIFIED")
        self.assertEqual(assessment["dimensions"]["broker_lease"]["state"], "VERIFIED")
        self.assertEqual(assessment["dimensions"]["host_lane"]["state"], "UNKNOWN")
        self.assertEqual(assessment["aggregate"]["state"], "UNKNOWN")
        self.assertFalse(assessment["acceptance_granted"])
        # Legacy CLI semantics are unchanged and still compose the same owners.
        status = self.fx.cli("status", RUN_ID, **env)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn('"state"', status.stdout)

    def test_cli_record_conflict_and_guard_refusals(self):
        self.fx.collect_complete()
        self.prepare_adjudication(verdict="PASS")
        env = {"POOL_LEDGER_PATH": str(self.fx.ledger_path),
               "CODEX_THREAD_ID": ROOT}
        args = ("quality-record", RUN_ID, "--root", ROOT, "--parent", PARENT,
                "--binding", str(self.fx.binding_path),
                "--collection", str(self.fx.destination / "receipt.json"),
                "--receipt-sha256", sha(self.fx.receipt_raw()),
                "--adjudication", str(self.fx.adjudication_path))
        first = self.fx.cli(*args, **env)
        self.assertEqual(first.returncode, 0, first.stderr)
        # A flipped verdict conflicts and never overwrites.
        self.prepare_adjudication(verdict="FAIL")
        second = self.fx.cli(*args, **env)
        self.assertEqual(second.returncode, 75)
        self.assertIn("collection_quality_conflict_existing_attestation", second.stderr)
        projection = self.fx.cli("quality-inspect", RUN_ID, "--root", ROOT,
                                 "--parent", PARENT, **env)
        self.assertEqual(json.loads(projection.stdout)["collected_source_quality"], "PASS")
        # A child label refuses before any IO.
        guarded = self.fx.cli(*args, **{**env, "CODEX_THREAD_ID": "child-thread-9"})
        self.assertEqual(guarded.returncode, 75)
        self.assertIn("quality_caller_not_original_root", guarded.stderr)


if __name__ == "__main__":
    unittest.main()
