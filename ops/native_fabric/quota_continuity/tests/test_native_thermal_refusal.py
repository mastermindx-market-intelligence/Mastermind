"""Adversarial read-only checks for the retained rc75 thermal refusal.

Fixture hashes replace the fixed historical allowlists only inside these tests.
The separate real-evidence diagnostic must use the committed production
constants. No fabricated live fixture proof is produced by this module.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "candidate"), str(ROOT / "source")]
import native_thermal_refusal_check as check
import pool_ledger


def encoded(value):
    return (json.dumps(value, sort_keys=True) + "\n").encode()


def process_receipt(label, *, returncode=0, started="2026-11-02T02:07:47.056Z",
                    ended="2026-11-02T02:07:47.200Z", pid=4242):
    return {
        "schema": check.PROCESS_SCHEMA, "label": label, "pid": pid, "pgid": pid,
        "started_at": started, "ended_at": ended, "returncode": returncode,
        "timed_out": False, "nice_requested": None, "nice_applied": False,
        "stdout_bytes": 0, "stdout_sha256": check.digest(b""), "stderr_bytes": 0,
        "stdout_truncated": False, "stderr_truncated": False,
        "runtime_failure_code": None,
        "cleanup": {
            "status": "not_needed", "reason": "normal_completion",
            "sigterm_sent": False, "sigkill_sent": False,
            "identity_verified": True, "census_proven": True, "residual_count": 0,
            "error_code": None, "stdout_capture_complete": True,
            "stderr_capture_complete": True, "stdin_delivery_complete": True,
            "stdout_capture_error": None, "stderr_capture_error": None,
            "stdin_delivery_error": None,
        },
    }


class ThermalFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-thermal-proof-",
                                                 dir=Path.home())
        self.base = Path(self.temp.name)
        self.here = self.base / "ext"
        self.state = self.here / "state/remote_sub"
        self.state.mkdir(parents=True, mode=0o700)
        self.lanes = self.here / "lanes"
        self.lanes.mkdir(mode=0o700)
        self.store = self.base / "native-code-releases"
        self.store.mkdir(mode=0o700)
        self.patches = contextlib.ExitStack()
        self.addCleanup(self.patches.close)
        self.addCleanup(self.temp.cleanup)

        # The frozen support closure: the support digest is the canonical digest
        # of the published manifest, and the policy digest is its pools.yaml.
        self.policy_sha = check.digest(b"fixture pools.yaml\n")
        self.source_bytes = {name: ("fixture historical bytes: " + name + "\n").encode()
                             for name in check.NATIVE_SOURCES}
        self.source_hashes = {name: check.digest(raw)
                              for name, raw in self.source_bytes.items()}
        self.support_files = dict(self.source_hashes)
        self.support_files["pools.yaml"] = self.policy_sha
        self.support_digest = check.digest(check.canonical(
            {"schema": "remote-support-code.v1", "files": self.support_files}))
        self.launch_sources = {name: self.source_hashes[name]
                               for name in check.LAUNCH_SOURCES}
        self.support_sources = {name: self.source_hashes[name]
                                 for name in check.SUPPORT_SOURCES}

        # The retained packet is exactly the frozen size.
        head = b"fixture packet for " + check.RUN.encode() + b"\n"
        packet = head + b"x" * (check.PACKET_BYTES - len(head) - 1) + b"\n"
        self.assertEqual(len(packet), check.PACKET_BYTES)
        request = {
            "schema": "mastermind.fabric_request_artifact.v1", "run_id": check.RUN,
            "root_id": check.ROOT, "parent_run_id": check.ROOT,
            "task_class": check.TASK_CLASS, "cwd": "~",
            "automatic_background_execution": False,
            "packet": check.RUN + ".request.packet",
            "packet_bytes": len(packet), "packet_sha256": check.digest(packet),
            "created_at": check.REQUEST_CREATED_AT,
        }
        request_raw = encoded(request)
        launch = {
            "schema": "mastermind.fabric_request_launch.v1", "run_id": check.RUN,
            "root_id": check.ROOT, "parent_run_id": check.ROOT,
            "packet_sha256": check.digest(packet),
            "state": "LAUNCH_ATTEMPT_RESERVED",
            "created_at": check.LAUNCH_CREATED_AT,
            "request_sha256": check.digest(request_raw),
            "capacity_handoff": True, "route": dict(check.ROUTE),
            "native_sources": dict(self.launch_sources),
        }
        launch_raw = encoded(launch)
        log = self.log_text()
        returned = {
            "schema": "mastermind.fabric_request_return.v1", "run_id": check.RUN,
            "root_id": check.ROOT, "parent_run_id": check.ROOT,
            "state": "NATIVE_CONTROLLER_RETURNED", "controller_rc": check.CONTROLLER_RC,
            "request_sha256": check.digest(request_raw),
            "launch_sha256": check.digest(launch_raw),
            "prelease_sha256": None, "log_sha256": check.digest(log),
        }
        continuation = {
            "schema": "mastermind.fabric_continuation.v1", "origin_run_id": check.RUN,
            "root_id": check.ROOT, "parent_run_id": check.ROOT,
            "deadline_ns": check.DEADLINE_NS, "max_attempts": check.MAX_ATTEMPTS,
            "wall_seconds": check.WALL_SECONDS, "background_execution": False,
        }
        finished = {
            "schema": "mastermind.fabric_continuation.v1", "origin_run_id": check.RUN,
            "effective_run_id": check.RUN, "root_id": check.ROOT,
            "parent_run_id": check.ROOT, "controller_rc": check.CONTROLLER_RC,
            "reason": check.CONTINUATION_REASON, "background_execution": False,
        }
        routing = encoded(process_receipt(check.RUN + ".routing"))
        controller = b"".join(encoded(row) for row in self.controller_rows())
        self.raw = {
            "request.json": request_raw, "request-launch.json": launch_raw,
            "request-return.json": encoded(returned), "request.packet": packet,
            "log": log, "support.json": encoded(self.support_files),
            "continuation-request.json": encoded(continuation),
            "continuation-finished.json": encoded(finished),
            "routing-process.jsonl": routing, "controller-process.jsonl": controller,
        }
        for name, raw in self.raw.items():
            path = self.artifact(name)
            path.write_bytes(raw)
            path.chmod(0o600)
        self.result_bytes = (check.RESULT_LINE + "\n").encode()
        self.result_path = self.lanes / check.RESULT_NAME
        self.result_path.write_bytes(self.result_bytes)
        self.result_path.chmod(0o600)

        # The compatible immutable closure carries the frozen source bytes.
        generation = self.build_generation()
        self.generation = generation
        self.build_broker()
        self.build_ledger()

        self.patches.enter_context(mock.patch.object(check, "HERE", self.here))
        self.patches.enter_context(mock.patch.object(
            check, "ARTIFACTS", {name: check.digest(raw)
                                 for name, raw in self.raw.items()}))
        self.patches.enter_context(mock.patch.object(
            check, "NATIVE_SOURCES", dict(self.source_hashes)))
        self.patches.enter_context(mock.patch.object(
            check, "LAUNCH_SOURCES", dict(self.launch_sources)))
        self.patches.enter_context(mock.patch.object(
            check, "SUPPORT_SOURCES", dict(self.support_sources)))
        self.patches.enter_context(mock.patch.object(
            check, "SUPPORT_DIGEST", self.support_digest))
        self.patches.enter_context(mock.patch.object(
            check, "POLICY_SHA256", self.policy_sha))
        self.patches.enter_context(mock.patch.object(
            check, "RESULT_SHA256", check.digest(self.result_bytes)))
        self.patches.enter_context(mock.patch.object(
            check, "COMPATIBLE_GENERATION", generation["name"]))
        self.patches.enter_context(mock.patch.object(
            check, "COMPATIBLE_RELEASE_SHA256", generation["release_sha256"]))
        self.patches.enter_context(mock.patch.object(
            check, "COMPATIBLE_GENERATION_FILES", generation["count"]))
        self.patches.enter_context(mock.patch.dict(
            os.environ, {"POOL_BROKER_DB": str(self.db_path)}))
        self.patches.enter_context(mock.patch.object(
            pool_ledger, "LEDGER_PATH", str(self.ledger_path)))

    # ── fixture construction ───────────────────────────────────────────────

    def artifact(self, name):
        return self.state / (check.RUN + "." + name)

    def log_text(self):
        prefix = "2026-11-02T02:07Z [remote_sub id=" + check.RUN + " host=" + check.HOST + "] "
        events = [
            "RUN_RESERVED explicit=1",
            "LEASE_WAIT pool=minimax wait=3600",
            "LEASE_OK pool=minimax",
            "SCP packet=" + check.RUN + ".request.packet support=executor-surface",
            "SUPPORT_VERSION_READY digest=" + self.support_digest
            + " policy=" + self.policy_sha,
            "LAUNCH stdout=~/lanes/ext/lanes_" + check.RUN
            + ".stdout rc_file=ext/lanes_" + check.RUN + ".rc cwd=~",
            "LAUNCH_ATTEMPT attempt=1",
            "POLL 1/7200 elapsed=0 file=~/lanes/ext/lanes_" + check.RUN + ".rc",
            "RC value=75 poll=1",
            "REMOTE_DONE rc=75",
            "RSYNC stdout=~/lanes/ext/lanes_" + check.RUN
            + ".stdout out=lanes_" + check.RUN + ".remote.stdout",
            "USAGE_RECEIPT_MISSING",
            "REMOTE_CLEANED transport=1 receipt_saved=0 usage_saved=0",
            "DONE rc=75 signal=admission reason=remote_admission_refused",
        ]
        return ("\n".join(prefix + event for event in events) + "\n").encode()

    def controller_rows(self):
        rows = []
        for label in check.CONTROLLER_LABELS:
            started = "2026-11-02T02:07:47.056Z"
            ended = "2026-11-02T02:07:47.400Z"
            if label == "commission-host-registry":
                started = "2026-11-02T02:07:46.400Z"
                ended = "2026-11-02T02:07:46.655Z"
            rows.append(process_receipt(
                label, returncode=1 if label == check.CONTROLLER_NONZERO_LABEL else 0,
                started=started, ended=ended, pid=4200 + len(rows)))
        return rows

    def build_generation(self):
        files = {}
        for name, raw in self.source_bytes.items():
            files["ext/" + name] = check.digest(raw)
        for number in range(89):
            name = "ext/filler-%03d.py" % number
            files[name] = check.digest(b"filler " + name.encode())
        files["pool"] = check.digest(b"fixture pool launcher\n")
        material = {
            "schema": "native-code-generation.v1", "files": files,
            "links": {"unit_fixture": "0"}, "stable_ext": str(self.here),
            "entrypoints": {"pool": "pool", "remote": "ext/remote_sub.sh",
                            "task": "ext/fabric_task.py"},
        }
        name = check.digest(check.canonical(material))
        directory = self.store / name
        (directory / "ext").mkdir(parents=True)
        for name_, raw in self.source_bytes.items():
            target = directory / "ext" / name_
            target.write_bytes(raw)
            target.chmod(0o555)
        for number in range(89):
            target = directory / "ext" / ("filler-%03d.py" % number)
            target.write_bytes(b"filler ext/" + target.name.encode())
            target.chmod(0o555)
        (directory / "pool").write_bytes(b"fixture pool launcher\n")
        (directory / "pool").chmod(0o555)
        release = encoded(dict(material, digest=name))
        (directory / "RELEASE.json").write_bytes(release)
        (directory / "RELEASE.json").chmod(0o444)
        (directory / "ext").chmod(0o555)
        directory.chmod(0o555)
        return {"name": name, "release_sha256": check.digest(release),
                "count": len(files)}

    def build_broker(self):
        self.db_path = self.base / "leases.sqlite"
        connection = sqlite3.connect(str(self.db_path))
        try:
            # The incumbent broker stores its leases in a write-ahead database.
            # The census must read it without ever creating the broker's own
            # write-ahead sidecars.
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """CREATE TABLE leases (
                    id TEXT PRIMARY KEY, orchestrator_id TEXT NOT NULL,
                    pool TEXT NOT NULL, account TEXT NOT NULL,
                    task_class TEXT NOT NULL, model TEXT NOT NULL DEFAULT '',
                    host TEXT NOT NULL, pid INTEGER NOT NULL,
                    granted_at REAL NOT NULL, ttl INTEGER NOT NULL,
                    last_heartbeat REAL NOT NULL, state TEXT NOT NULL,
                    renewable INTEGER NOT NULL DEFAULT 1,
                    quota_scope TEXT, quota_outcome_sha256 TEXT)""")
            connection.execute(
                "INSERT INTO leases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (check.LEASE_ID, check.ROOT, check.POOL, check.ACCOUNT,
                 check.TASK_CLASS_BROKER, check.ROUTE["MODEL"], check.HOST,
                 check.LEASE_PID, check.LEASE_GRANTED_AT, check.LEASE_TTL,
                 check.LEASE_LAST_HEARTBEAT, check.LEASE_STATE,
                 check.LEASE_RENEWABLE, check.LEASE_QUOTA_SCOPE, None))
            connection.commit()
        finally:
            connection.close()
        self.db_path.chmod(0o644)
        self.assertFalse(Path(str(self.db_path) + "-wal").exists())
        self.assertFalse(Path(str(self.db_path) + "-shm").exists())

    def lease_row(self, **overrides):
        row = {
            "id": check.LEASE_ID, "orchestrator_id": check.ROOT, "pool": check.POOL,
            "account": check.ACCOUNT, "task_class": check.TASK_CLASS_BROKER,
            "model": check.ROUTE["MODEL"], "host": check.HOST, "pid": check.LEASE_PID,
            "granted_at": check.LEASE_GRANTED_AT, "ttl": check.LEASE_TTL,
            "last_heartbeat": check.LEASE_LAST_HEARTBEAT, "state": check.LEASE_STATE,
            "renewable": check.LEASE_RENEWABLE,
            "quota_scope": check.LEASE_QUOTA_SCOPE, "quota_outcome_sha256": None,
        }
        row.update(overrides)
        return row

    def restore_lease(self, **overrides):
        """Put exactly the frozen broker row back before each census case."""
        connection = sqlite3.connect(str(self.db_path))
        try:
            connection.execute("DELETE FROM leases")
            row = self.lease_row(**overrides)
            connection.execute(
                "INSERT INTO leases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                tuple(row[name] for name in (
                    "id", "orchestrator_id", "pool", "account", "task_class",
                    "model", "host", "pid", "granted_at", "ttl", "last_heartbeat",
                    "state", "renewable", "quota_scope", "quota_outcome_sha256")))
            connection.commit()
        finally:
            connection.close()

    def build_ledger(self):
        self.ledger_path = self.base / "ledger.jsonl"
        row = {
            "ts": 1793585290, "pool": check.POOL, "key": check.ACCOUNT,
            "window_id": "fixture-window", "task_class": check.TASK_CLASS_BROKER,
            "rc": check.CONTROLLER_RC, "tokens": None, "signal": check.CONTROLLER_SIGNAL,
            "reason": check.CONTROLLER_REASON, "escalation_reason": None,
            "run_id": check.RUN, "accepted_by": None, "review_rejected": False,
            "scope_violation": False, "retries": 0, "escalated": False,
            "wall_s": 5, "model": check.ROUTE["MODEL"], "root_id": check.ROOT,
            "parent_run_id": check.ROOT,
        }
        self.ledger_path.write_bytes(encoded(row))
        self.ledger_path.chmod(0o644)

    # ── helpers ────────────────────────────────────────────────────────────

    def qualify(self):
        return check.check_original(check.RUN, check.ROOT)

    def snapshot(self):
        return {str(path.relative_to(self.base)): (path.read_bytes(),
                                                  check.digest(path.read_bytes()))
                for path in sorted(self.base.rglob("*")) if path.is_file()}

    def rewrite(self, name, raw):
        path = self.artifact(name)
        path.write_bytes(raw)
        path.chmod(0o600)
        self.refresh_digest(name, raw)

    def refresh_digest(self, name, raw):
        digests = dict(check.ARTIFACTS)
        digests[name] = check.digest(raw)
        self.patches.enter_context(mock.patch.object(check, "ARTIFACTS", digests))

    # ── tests ──────────────────────────────────────────────────────────────


class ThermalRefusalTests(ThermalFixture, unittest.TestCase):

    def test_positive_proof_is_read_only_and_grants_no_authority(self):
        before = self.snapshot()
        with mock.patch("subprocess.run", side_effect=AssertionError("no process")), \
             mock.patch("subprocess.Popen", side_effect=AssertionError("no process")):
            proof = self.qualify()
        self.assertEqual(before, self.snapshot())
        self.assertEqual(proof["predicate"], check.PREDICATE)
        self.assertEqual(proof["controller_rc"], 75)
        self.assertEqual(proof["signal"], "admission")
        self.assertEqual(proof["result_bytes"], 241)
        for field in ("canonical_state_changed", "reconciliation_performed",
                      "retry_allowed", "acceptance_eligible", "review_result_available",
                      "telemetry_transport_absence_claimed",
                      "remote_cryptographic_attestation_claimed",
                      "original_selected_generation_recorded"):
            self.assertIs(proof[field], False)
        self.assertIs(proof["same_os_principal_native_evidence_model"], True)
        self.assertEqual(proof["new_work_admission"], "UNCHANGED")
        lease = proof["reconstructed_lease"]
        self.assertEqual(lease["lease_id"], check.LEASE_ID)
        self.assertEqual(lease["state"], "released")
        self.assertIs(lease["lease_id_bound_by_run_artifact"], False)
        self.assertIs(lease["pid_corroboration_only"], True)
        self.assertIs(lease["original_acquisition_receipt_claimed"], False)
        self.assertIs(lease["release_before_original_return_claimed"], False)
        self.assertEqual(proof["ledger_lineage_state"], "VERIFIED_TERMINAL")
        self.assertEqual(len(proof["proof_sha256"]), 64)

    def test_unrelated_run_or_root_is_refused_without_touching_evidence(self):
        before = self.snapshot()
        for run, root in [("other-run-20261102", check.ROOT),
                          (check.RUN, "other-root"), (check.RUN, None)]:
            with self.subTest(run=run, root=root), self.assertRaises(check.Unqualified):
                check.check_original(run, root)
        self.assertEqual(before, self.snapshot())

    def test_changed_artifact_bytes_are_refused_by_the_frozen_digest(self):
        path = self.artifact("request.json")
        path.write_bytes(self.raw["request.json"] + b" ")
        path.chmod(0o600)
        with self.assertRaisesRegex(check.Unqualified, "historical_artifact_digest"):
            self.qualify()

    def test_forged_or_post_start_evidence_is_refused(self):
        forged = json.loads(self.raw["request.json"])
        forged["task_class"] = "review"
        self.rewrite("request.json", encoded(forged))
        with self.assertRaisesRegex(check.Unqualified, "request_binding"):
            self.qualify()

    def test_semantic_relationship_checks_fail_even_when_digests_are_rebound(self):
        mutations = [
            ("request.json", "root_id", "other-root"),
            ("request.json", "task_class", "review"),
            ("request.json", "cwd", "/tmp"),
            ("request.json", "automatic_background_execution", True),
            ("request-launch.json", "state", "LAUNCHED"),
            ("request-launch.json", "capacity_handoff", False),
            ("request-launch.json", "route", {"HOST": "ubuntu0"}),
            ("request-launch.json", "native_sources", {}),
            ("request-return.json", "controller_rc", True),
            ("request-return.json", "prelease_sha256", "a" * 64),
            ("continuation-request.json", "max_attempts", True),
            ("continuation-finished.json", "effective_run_id", "successor"),
            ("continuation-finished.json", "reason", "terminal_return"),
        ]
        for suffix, key, value in mutations:
            with self.subTest(suffix=suffix, key=key):
                changed = dict(self.raw)
                record = json.loads(changed[suffix])
                record[key] = value
                changed[suffix] = encoded(record)
                with self.assertRaises(check.Unqualified):
                    check.validate_chain(changed)

    def test_packet_and_process_mismatches_are_refused(self):
        changed = dict(self.raw)
        changed["request.packet"] = changed["request.packet"] + b"x"
        with self.assertRaisesRegex(check.Unqualified, "request_binding"):
            check.validate_chain(changed)
        lines = self.raw["controller-process.jsonl"].splitlines()
        for index, mutate, expected in (
                (0, lambda row: row["cleanup"].update(residual_count=1),
                 "process_cleanup_unproven"),
                (0, lambda row: row.update(label="commission-unknown"),
                 "process_receipt_label"),
                (0, lambda row: row.update(returncode=0, timed_out=True),
                 "process_receipt_unqualified"),
                (0, lambda row: row.update(stdout_truncated=True),
                 "process_receipt_unqualified"),
                (0, lambda row: row.update(runtime_failure_code="crashed"),
                 "process_receipt_unqualified"),
                (12, lambda row: row.update(returncode=0),
                 "process_receipt_returncode")):
            with self.subTest(expected=expected):
                rows = [json.loads(line) for line in lines]
                mutate(rows[index])
                mutated = dict(self.raw)
                mutated["controller-process.jsonl"] = b"".join(encoded(row) for row in rows)
                with self.assertRaisesRegex(check.Unqualified, expected):
                    check.validate_chain(mutated)

    def test_log_must_show_one_refused_admission_and_no_retry_or_success(self):
        text = self.raw["log"].decode()
        broken = text.replace("DONE rc=75 signal=admission reason=remote_admission_refused",
                              "DONE rc=0 signal=ok")
        with self.assertRaises(check.Unqualified):
            check.validate_chain(dict(self.raw, log=broken.encode()))
        broken = text.replace("REMOTE_CLEANED transport=1 receipt_saved=0 usage_saved=0",
                              "REMOTE_CLEANED transport=1 receipt_saved=1 usage_saved=1")
        with self.assertRaises(check.Unqualified):
            check.validate_chain(dict(self.raw, log=broken.encode()))
        broken = text.replace("USAGE_RECEIPT_MISSING", "USAGE_RECEIPT_SAVED")
        with self.assertRaises(check.Unqualified):
            check.validate_chain(dict(self.raw, log=broken.encode()))
        broken = text + "2026-11-02T02:08Z [remote_sub id=" + check.RUN \
            + " host=" + check.HOST + "] DONE rc=0 signal=ok\n"
        with self.assertRaises(check.Unqualified):
            check.validate_chain(dict(self.raw, log=broken.encode()))
        broken = text.replace("host=" + check.HOST, "host=ubuntu0")
        with self.assertRaises(check.Unqualified):
            check.validate_chain(dict(self.raw, log=broken.encode()))

    def test_missing_extra_or_late_artifact_is_refused(self):
        saved = self.artifact("request.json").read_bytes()
        self.artifact("request.json").unlink()
        with self.assertRaises(check.Unqualified):
            self.qualify()
        self.artifact("request.json").write_bytes(saved)
        self.artifact("request.json").chmod(0o600)
        self.artifact("usage.json").write_bytes(b"late usage receipt")
        self.artifact("usage.json").chmod(0o600)
        with self.assertRaises(check.Unqualified):
            self.qualify()
        self.artifact("usage.json").unlink()
        self.artifact("successor.json").write_bytes(b"{}")
        self.artifact("successor.json").chmod(0o600)
        with self.assertRaises(check.Unqualified):
            self.qualify()

    def test_extra_lane_artifact_is_refused(self):
        other = self.lanes / (check.RUN + ".usage.json")
        other.write_bytes(b"late lane usage")
        other.chmod(0o600)
        with self.assertRaises(check.Unqualified):
            self.qualify()

    def test_symlink_hardlink_unsafe_mode_and_ownership_are_refused(self):
        path = self.artifact("request.json")
        saved = path.read_bytes()
        for case in ("symlink", "hardlink", "public", "oversize"):
            with self.subTest(case=case):
                path.unlink()
                path.write_bytes(saved)
                path.chmod(0o600)
                peer = self.base / ("peer-" + case)
                if case == "symlink":
                    path.rename(peer)
                    path.symlink_to(peer)
                elif case == "hardlink":
                    os.link(path, peer)
                elif case == "public":
                    path.chmod(0o644)
                else:
                    path.write_bytes(b"x" * 70000)
                with self.assertRaises((OSError, check.Unqualified)):
                    self.qualify()
        path.unlink()
        path.write_bytes(saved)
        path.chmod(0o600)

    def test_symlinked_state_parent_is_refused(self):
        original = self.here / "state"
        other = self.here / "saved-state"
        original.rename(other)
        original.symlink_to(other, target_is_directory=True)
        with self.assertRaises((OSError, check.Unqualified)):
            self.qualify()

    def test_changed_source_bytes_in_the_compatible_generation_are_refused(self):
        target = self.generation["name"]
        source = self.store / target / "ext/remote_sub.sh"
        source.chmod(0o755)
        source.write_bytes(source.read_bytes() + b"changed")
        source.chmod(0o555)
        with self.assertRaisesRegex(check.Unqualified, "compatible_source_bytes"):
            self.qualify()

    def test_compatible_generation_absence_is_a_refusal_not_an_invented_proof(self):
        directory = self.store / self.generation["name"]
        directory.chmod(0o755)
        for child in sorted(directory.rglob("*"), reverse=True):
            child.chmod(0o755 if child.is_dir() else 0o644)
        shutil.rmtree(directory)
        with self.assertRaises((OSError, check.Unqualified)):
            self.qualify()

    def test_cross_record_replacement_with_identical_bytes_is_refused(self):
        real = check.EvidenceReadSet.read

        def racing(reader, path, **kwargs):
            data = real(reader, path, **kwargs)
            if Path(path) == self.artifact("request-launch.json"):
                target = self.artifact("request.json")
                replacement = self.base / "replacement"
                replacement.write_bytes(target.read_bytes())
                replacement.chmod(0o600)
                os.replace(replacement, target)
            return data
        with mock.patch.object(check.EvidenceReadSet, "read", racing):
            with self.assertRaisesRegex(check.Unqualified, "evidence_changed"):
                self.qualify()

    def test_added_artifact_after_chain_validation_is_refused(self):
        real = check.validate_chain

        def racing(raw):
            result = real(raw)
            self.artifact("prelease.json").write_bytes(b"{}")
            return result
        with mock.patch.object(check, "validate_chain", racing):
            with self.assertRaises(check.Unqualified):
                self.qualify()

    def test_broker_census_requires_exactly_one_released_row(self):
        cases = [
            ("zero", {"delete": True}, "broker_census_row_count:0"),
            ("two", {"extra": True}, "broker_census_row_count:2"),
            ("wrong", {"id": "000000000000"}, "broker_lease_row_unqualified"),
            ("unreleased", {"state": "held"}, "broker_lease_row_unqualified"),
            ("wrong_pid", {"pid": check.LEASE_PID + 1}, "broker_lease_row_unqualified"),
            ("wrong_grant", {"granted_at": check.LEASE_GRANTED_AT + 1.0},
             "broker_lease_row_unqualified"),
            ("wrong_ttl", {"ttl": check.LEASE_TTL + 1}, "broker_lease_row_unqualified"),
            ("wrong_heartbeat", {"last_heartbeat": check.LEASE_LAST_HEARTBEAT + 1.0},
             "broker_lease_row_unqualified"),
            ("wrong_renewable", {"renewable": 0}, "broker_lease_row_unqualified"),
            ("wrong_scope", {"quota_scope": "other:default"},
             "broker_lease_row_unqualified"),
            ("wrong_quota_outcome", {"quota_outcome_sha256": "a" * 64},
             "broker_lease_row_unqualified"),
        ]
        for name, overrides, expected in cases:
            with self.subTest(case=name):
                self.restore_lease()
                if overrides.get("delete"):
                    connection = sqlite3.connect(str(self.db_path))
                    try:
                        connection.execute("DELETE FROM leases")
                        connection.commit()
                    finally:
                        connection.close()
                elif overrides.get("extra"):
                    connection = sqlite3.connect(str(self.db_path))
                    try:
                        row = self.lease_row(id="aaaaaaaaaaaa",
                                             granted_at=check.LEASE_GRANTED_AT + 0.1)
                        connection.execute(
                            "INSERT INTO leases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            tuple(row[name_] for name_ in (
                                "id", "orchestrator_id", "pool", "account",
                                "task_class", "model", "host", "pid", "granted_at",
                                "ttl", "last_heartbeat", "state", "renewable",
                                "quota_scope", "quota_outcome_sha256")))
                        connection.commit()
                    finally:
                        connection.close()
                elif overrides:
                    self.restore_lease(**overrides)
                with self.assertRaisesRegex(check.Unqualified, expected):
                    self.qualify()

    def test_broker_census_detects_a_write_during_the_census(self):
        real_sidecars = check._sidecars
        calls = 0

        def racing(path):
            nonlocal calls
            calls += 1
            observed = real_sidecars(path)
            if calls == 2:
                # A committed write-ahead frame changes the write-ahead log.
                return {"-wal": (1, 1, 1), "-shm": observed["-shm"]}
            return observed
        with mock.patch.object(check, "_sidecars", racing):
            with self.assertRaisesRegex(check.Unqualified, "broker_census_mutated"):
                self.qualify()

    def test_broker_census_never_creates_the_broker_write_ahead_sidecars(self):
        before = sorted(path.name for path in self.base.iterdir())
        proof = self.qualify()
        after = sorted(path.name for path in self.base.iterdir())
        self.assertEqual(before, after)
        self.assertFalse(Path(str(self.db_path) + "-wal").exists())
        self.assertFalse(Path(str(self.db_path) + "-shm").exists())
        self.assertIs(proof["broker_census"]["sidecars_created_by_census"], False)

    def test_broker_census_refuses_a_populated_log_without_the_broker_index(self):
        # A populated write-ahead log without the broker's shared-memory index
        # cannot be read completely without recovering it, so the census
        # refuses instead of creating the index itself.
        wal = Path(str(self.db_path) + "-wal")
        wal.write_bytes(b"\x37\x7f\x06\x82" + b"\x00" * 28)
        wal.chmod(0o644)
        with self.assertRaisesRegex(check.Unqualified, "broker_sidecar_absent"):
            self.qualify()

    def test_broker_census_rejects_a_lease_outside_the_bounded_interval(self):
        self.restore_lease(granted_at=check.LAUNCH_CREATED_AT - 600.0)
        with self.assertRaisesRegex(check.Unqualified, "broker_census_row_count:0"):
            self.qualify()

    def test_ledger_identity_must_be_the_verified_root_and_parent(self):
        self.ledger_path.write_bytes(encoded({
            "ts": 1793585290, "pool": check.POOL, "key": check.ACCOUNT,
            "window_id": "fixture-window", "task_class": check.TASK_CLASS_BROKER,
            "rc": check.CONTROLLER_RC, "signal": check.CONTROLLER_SIGNAL,
            "run_id": check.RUN, "root_id": "other-root", "parent_run_id": "other-root",
        }))
        with self.assertRaisesRegex(check.Unqualified, "ledger_execution_identity"):
            self.qualify()

    def test_result_bytes_must_be_the_frozen_refusal_line(self):
        self.result_path.write_bytes(b"provider success\n")
        self.result_path.chmod(0o600)
        with self.assertRaises(check.Unqualified):
            self.qualify()


class ThermalReconciliationTests(ThermalFixture, unittest.TestCase):
    """The explicit reconciler records one disposition and nothing else."""

    def receipt(self):
        import native_thermal_refusal_reconcile as reconcile
        return reconcile.receipt_path()

    def test_reconciliation_requires_an_exact_fresh_proof_before_writing(self):
        import native_thermal_refusal_reconcile as reconcile
        self.assertFalse(self.receipt().exists())
        for bad in ("0" * 64, "", None, True):
            with self.subTest(bad=bad), self.assertRaises(check.Unqualified):
                reconcile.reconcile_original(check.RUN, check.ROOT, bad)
        self.assertFalse(self.receipt().exists())

    def test_unrelated_run_is_never_reconciled(self):
        import native_thermal_refusal_reconcile as reconcile
        with self.assertRaises(check.Unqualified):
            reconcile.reconcile_original("other-run-20261102", check.ROOT, "a" * 64)
        self.assertFalse(self.receipt().exists())

    def test_the_read_only_check_still_qualifies_after_a_receipt_exists(self):
        import native_thermal_refusal_reconcile as reconcile
        proof = self.qualify()
        reconcile.reconcile_original(check.RUN, check.ROOT, proof["proof_sha256"])
        self.assertTrue(self.receipt().exists())
        repeated = self.qualify()
        self.assertEqual(repeated["proof_sha256"], proof["proof_sha256"])

    def test_recorded_disposition_preserves_the_original_failure(self):
        import native_thermal_refusal_reconcile as reconcile
        import fabric_task
        proof = self.qualify()
        original = {name: (self.artifact(name).read_bytes(),
                            check.digest(self.artifact(name).read_bytes()))
                    for name in self.raw}
        with mock.patch("subprocess.run", side_effect=AssertionError("no dispatch")):
            result = reconcile.reconcile_original(check.RUN, check.ROOT,
                                                  proof["proof_sha256"])
        self.assertEqual(result["action"], "RECORDED")
        self.assertIs(result["worker_dispatch_performed"], False)
        self.assertIs(result["retry_allowed"], False)
        self.assertEqual(result["new_work_admission"], "UNCHANGED")
        self.assertEqual(original, {
            name: (self.artifact(name).read_bytes(),
                   check.digest(self.artifact(name).read_bytes()))
            for name in self.raw})
        with mock.patch.object(fabric_task, "HERE", self.here):
            status = fabric_task.inspect_run(check.RUN)
        self.assertEqual((status["state"], status["rc"], status["signal"]),
                         ("TERMINAL", 75, "admission"))
        self.assertEqual(status["reason"], "remote_admission_refused")
        self.assertEqual(status["root_id"], check.ROOT)
        self.assertEqual(status["parent_run_id"], check.ROOT)
        self.assertIs(status["result_available"], True)
        self.assertEqual(status["result_bytes"], 241)
        self.assertIs(status["execution_absence_proven"], True)
        self.assertIs(status["same_run_replay_allowed"], False)
        self.assertIs(status["retry_allowed"], False)
        self.assertIs(status["acceptance_eligible"], False)
        self.assertIsNone(status["accepted"])
        self.assertEqual(status["acceptance_state"], "UNVERIFIED")
        self.assertEqual(status["new_work_admission"], "UNCHANGED")
        self.assertEqual(status["reconciliation"]["disposition"],
                         reconcile.DISPOSITION)

    def test_check_and_status_have_no_effects_and_start_no_work(self):
        import fabric_task
        before = self.snapshot()
        with mock.patch("subprocess.run", side_effect=AssertionError("no process")), \
             mock.patch("subprocess.Popen", side_effect=AssertionError("no process")), \
             mock.patch.object(fabric_task, "request",
                               side_effect=AssertionError("no dispatch")), \
             mock.patch.object(fabric_task, "HERE", self.here):
            proof = self.qualify()
            status = fabric_task.inspect_run(check.RUN)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(status["state"], "TERMINAL")
        self.assertIs(status["retry_allowed"] if "retry_allowed" in status else False, False)
        self.assertIs(proof["canonical_state_changed"], False)

    def test_identical_existing_receipt_is_read_only(self):
        import native_thermal_refusal_reconcile as reconcile
        proof = self.qualify()
        reconcile.reconcile_original(check.RUN, check.ROOT, proof["proof_sha256"])
        path = self.receipt()
        before = (path.read_bytes(), check.digest(path.read_bytes()))
        real_open = os.open

        def no_write(target, flags, *args, **kwargs):
            if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
                raise AssertionError("existing receipt must not be reopened for writing")
            return real_open(target, flags, *args, **kwargs)
        with mock.patch("os.open", no_write):
            result = reconcile.reconcile_original(check.RUN, check.ROOT,
                                                  proof["proof_sha256"])
        self.assertEqual(result["action"], "ALREADY_RECORDED")
        self.assertIs(result["receipt_written_by_this_call"], False)
        self.assertEqual(before, (path.read_bytes(), check.digest(path.read_bytes())))

    def test_partial_receipt_is_preserved_and_never_repairs_itself(self):
        import native_thermal_refusal_reconcile as reconcile
        import fabric_task
        proof = self.qualify()
        path = self.receipt()
        path.write_bytes(b'{"schema":')
        path.chmod(0o600)
        before = (path.read_bytes(), check.digest(path.read_bytes()))
        with self.assertRaises(check.Unqualified):
            reconcile.reconcile_original(check.RUN, check.ROOT, proof["proof_sha256"])
        self.assertEqual(before, (path.read_bytes(), check.digest(path.read_bytes())))
        with mock.patch.object(fabric_task, "HERE", self.here):
            status = fabric_task.inspect_run(check.RUN)
        self.assertEqual(status["state"], "STATUS_UNREADABLE")
        self.assertIsNone(status["root_id"])
        self.assertIsNone(status["accepted"])

    def test_interrupted_receipt_write_keeps_a_partial_artifact_unqualified(self):
        import native_thermal_refusal_reconcile as reconcile
        proof = self.qualify()
        real_write = os.write
        calls = 0

        def interrupted(fd, data):
            nonlocal calls
            calls += 1
            if calls == 1:
                return real_write(fd, data[:17])
            raise OSError("injected publication interruption")
        with mock.patch("os.write", interrupted), self.assertRaises(
                reconcile.PublicationUnqualified):
            reconcile.reconcile_original(check.RUN, check.ROOT, proof["proof_sha256"])
        path = self.receipt()
        self.assertEqual(path.stat().st_size, 17)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(check.Unqualified):
            reconcile.status_from_receipt()

    def test_complete_write_with_fsync_error_is_settled_only_by_fresh_readback(self):
        import native_thermal_refusal_reconcile as reconcile
        proof = self.qualify()
        with mock.patch("os.fsync", side_effect=OSError("injected fsync failure")):
            with self.assertRaises(reconcile.PublicationUnqualified) as failure:
                reconcile.reconcile_original(check.RUN, check.ROOT, proof["proof_sha256"])
        self.assertEqual(failure.exception.effect_state, "EFFECT_UNKNOWN")
        path = self.receipt()
        before = (path.read_bytes(), check.digest(path.read_bytes()))
        status = reconcile.status_from_receipt()
        self.assertEqual(status["state"], "TERMINAL")
        self.assertEqual(status["rc"], 75)
        self.assertIs(status["retry_allowed"], False)
        self.assertIs(status["result_available"], True)
        self.assertEqual(before, (path.read_bytes(), check.digest(path.read_bytes())))

    def test_cli_output_failure_after_publication_never_claims_not_applied(self):
        import native_thermal_refusal_reconcile as reconcile
        import fabric_task
        proof = self.qualify()
        real_json = fabric_task._json
        calls = 0

        def failed_output(value):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("injected acknowledgment output failure")
            return real_json(value)
        with mock.patch.object(fabric_task, "_json", failed_output), \
             contextlib.redirect_stdout(io.StringIO()) as stdout, \
             contextlib.redirect_stderr(io.StringIO()) as stderr:
            rc = fabric_task.main(["reconcile-thermal-refusal", check.RUN,
                                   "--root", check.ROOT,
                                   "--expected-proof-sha256", proof["proof_sha256"]])
        self.assertEqual(rc, 78)
        self.assertNotIn("NOT_APPLIED", stdout.getvalue() + stderr.getvalue())
        self.assertIn("EFFECT_UNKNOWN", stderr.getvalue())
        self.assertEqual(calls, 1)
        status = reconcile.status_from_receipt()
        self.assertEqual(status["state"], "TERMINAL")
        self.assertIs(status["retry_allowed"], False)

    def test_cli_flush_failure_preserves_the_receipt(self):
        import native_thermal_refusal_reconcile as reconcile
        import fabric_task
        proof = self.qualify()
        path = self.receipt()

        class FailedFlush(io.StringIO):
            def __init__(self):
                super().__init__()
                self.flush_calls = 0
                self.receipt_before_failure = None

            def flush(self):
                self.flush_calls += 1
                self.receipt_before_failure = (path.read_bytes(),
                                               check.digest(path.read_bytes()))
                raise BrokenPipeError("injected buffered acknowledgment flush failure")
        stdout = FailedFlush()
        with contextlib.redirect_stdout(stdout), \
             contextlib.redirect_stderr(io.StringIO()) as stderr:
            rc = fabric_task.main(["reconcile-thermal-refusal", check.RUN,
                                   "--root", check.ROOT,
                                   "--expected-proof-sha256", proof["proof_sha256"]])
        self.assertFalse(stdout.closed)
        self.assertEqual(json.loads(stdout.getvalue())["action"], "RECORDED")
        self.assertEqual(rc, 78)
        self.assertEqual(stdout.flush_calls, 1)
        self.assertIn("THERMAL_REFUSAL_RECONCILIATION_RETURN_UNDELIVERED: EFFECT_UNKNOWN",
                      stderr.getvalue())
        self.assertNotIn("NOT_APPLIED", stdout.getvalue() + stderr.getvalue())
        self.assertIsNotNone(stdout.receipt_before_failure)
        self.assertEqual(stdout.receipt_before_failure,
                         (path.read_bytes(), check.digest(path.read_bytes())))

    def test_cli_check_does_not_call_request_or_change_status(self):
        import fabric_task
        with mock.patch.object(check, "check_original",
                               return_value={"retry_allowed": False}) as called, \
             mock.patch.object(fabric_task, "request",
                               side_effect=AssertionError("no dispatch")), \
             mock.patch("subprocess.run", side_effect=AssertionError("no process")), \
             contextlib.redirect_stdout(io.StringIO()) as stdout:
            rc = fabric_task.main(["check-thermal-refusal", check.RUN,
                                   "--root", check.ROOT])
        self.assertEqual(rc, 0)
        called.assert_called_once_with(check.RUN, check.ROOT)
        self.assertEqual(json.loads(stdout.getvalue()), {"retry_allowed": False})

    def test_reconciliation_cli_distinguishes_refusal_from_ambiguous_publication(self):
        import native_thermal_refusal_reconcile as reconcile
        import fabric_task
        cases = [(check.Unqualified("proof mismatch"), "NOT_APPLIED"),
                 (reconcile.PublicationUnqualified("interrupted"), "EFFECT_UNKNOWN")]
        for error, expected in cases:
            with self.subTest(expected=expected):
                with mock.patch.object(reconcile, "reconcile_original",
                                       side_effect=error), \
                     contextlib.redirect_stdout(io.StringIO()) as stdout, \
                     contextlib.redirect_stderr(io.StringIO()):
                    rc = fabric_task.main(["reconcile-thermal-refusal", check.RUN,
                                           "--root", check.ROOT,
                                           "--expected-proof-sha256", "a" * 64])
                self.assertEqual(rc, 78)
                response = json.loads(stdout.getvalue())
                self.assertEqual(response["effect_state"], expected)
                self.assertIs(response["retry_allowed"], False)
                self.assertIs(response["worker_dispatch_performed"], False)

    def test_late_lane_artifact_invalidates_a_recorded_status(self):
        import native_thermal_refusal_reconcile as reconcile
        proof = self.qualify()
        reconcile.reconcile_original(check.RUN, check.ROOT, proof["proof_sha256"])
        extra = self.lanes / (check.RUN + ".usage.json")
        extra.write_bytes(b"late usage receipt")
        extra.chmod(0o600)
        with self.assertRaises(check.Unqualified):
            reconcile.status_from_receipt()


if __name__ == "__main__":
    unittest.main()
