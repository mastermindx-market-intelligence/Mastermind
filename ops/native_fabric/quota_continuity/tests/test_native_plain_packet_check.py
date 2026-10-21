"""Adversarial read-only checks; every evidence byte lives in a private fixture.

Fixture hashes replace the fixed historical allowlists only inside these tests.
The separate real-evidence diagnostic must use the committed production constants.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "candidate"), str(ROOT / "source")]
import native_plain_packet_check as check


def encoded(value):
    return (json.dumps(value, sort_keys=True) + "\n").encode()


class HistoricalCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-packet-proof-", dir=Path.home())
        self.base = Path(self.temp.name)
        self.here = self.base / "ext"
        self.state = self.here / "state/remote_sub"
        self.state.mkdir(parents=True, mode=0o700)
        (self.here / "lanes").mkdir(mode=0o700)
        self.store = self.base / "native-code-releases"
        self.store.mkdir(mode=0o700)
        self.source_bytes = {name: ("fixture historical bytes: " + name + "\n").encode()
                             for name in check.SOURCES}
        self.source_hashes = {name: check.digest(raw) for name, raw in self.source_bytes.items()}
        packet = ("Review frozen commit " + check.SUBJECT + "\nRoot " + check.ROOT + "\n").encode()
        request = dict(schema="mastermind.fabric_request_artifact.v1", run_id=check.RUN,
                       root_id=check.ROOT, parent_run_id=check.ROOT, task_class="review",
                       cwd="~", automatic_background_execution=False,
                       packet=check.RUN + ".request.packet", packet_bytes=len(packet),
                       packet_sha256=check.digest(packet))
        request_raw = encoded(request)
        launch = dict(schema="mastermind.fabric_request_launch.v1", run_id=check.RUN,
                      root_id=check.ROOT, parent_run_id=check.ROOT,
                      state="LAUNCH_ATTEMPT_RESERVED", capacity_handoff=True,
                      route=dict(HOST="ubuntu0", KEY="Chris", MODE="qwen", MODEL="qwen3.8-max",
                                 POOL="bailian", REASON="execute_order_bailian"),
                      native_sources={name: self.source_hashes[name] for name in (
                          "remote_sub.sh", "lease_broker.py", "quota_circuit.py")},
                      request_sha256=check.digest(request_raw), packet_sha256=check.digest(packet))
        launch_raw = encoded(launch)
        prefix = "2026-10-21T04:42Z [remote_sub id=" + check.RUN + " host=ubuntu0] "
        log = (prefix + "RUN_RESERVED explicit=1\n" + prefix
               + "PLAIN_PACKET_RETENTION_REFUSED rc=78 before_lease=1\n").encode()
        returned = dict(schema="mastermind.fabric_request_return.v1", run_id=check.RUN,
                        root_id=check.ROOT, parent_run_id=check.ROOT, controller_rc=78,
                        state="NATIVE_CONTROLLER_RETURNED", prelease_sha256=None,
                        request_sha256=check.digest(request_raw),
                        launch_sha256=check.digest(launch_raw), log_sha256=check.digest(log))
        continuation = dict(schema="mastermind.fabric_continuation.v1", origin_run_id=check.RUN,
                            root_id=check.ROOT, parent_run_id=check.ROOT,
                            deadline_ns=123456, max_attempts=3, wall_seconds=7200,
                            background_execution=False)
        finished = dict(schema="mastermind.fabric_continuation.v1", origin_run_id=check.RUN,
                        effective_run_id=check.RUN, root_id=check.ROOT,
                        parent_run_id=check.ROOT, controller_rc=78,
                        reason="continuation_evidence_unqualified", background_execution=False)
        stdout = (b"POOL=bailian KEY=Chris MODEL=qwen3.8-max "
                  b"REASON=execute_order_bailian HOST=ubuntu0 MODE=qwen\n")
        routing = dict(schema="mastermind.local_owned_process_receipt.v1",
                       label=check.RUN + ".routing", returncode=0, timed_out=False,
                       stdout_truncated=False, stderr_truncated=False, runtime_failure_code=None,
                       pid=123, pgid=123, stdout_bytes=len(stdout), stdout_sha256=check.digest(stdout),
                       stderr_bytes=0, cleanup=dict(identity_verified=True, census_proven=True,
                           residual_count=0, status="not_needed", reason="normal_completion",
                           error_code=None, stdout_capture_complete=True, stderr_capture_complete=True,
                           stdin_delivery_complete=True, stdout_capture_error=None,
                           stderr_capture_error=None, stdin_delivery_error=None))
        self.raw = {"request.json": request_raw, "request-launch.json": launch_raw,
                    "request-return.json": encoded(returned), "request.packet": packet, "log": log,
                    "continuation-request.json": encoded(continuation),
                    "continuation-finished.json": encoded(finished),
                    "routing-process.jsonl": encoded(routing)}
        for name, raw in self.raw.items():
            self.artifact(name).write_bytes(raw)
            self.artifact(name).chmod(0o600)
        generations = []
        for number in range(2):
            material = dict(schema="native-code-generation.v1", files={
                "ext/" + name: sha for name, sha in self.source_hashes.items()},
                links={"unit_fixture": str(number)}, stable_ext=str(self.here),
                entrypoints=dict(pool="pool", remote="ext/remote_sub.sh", task="ext/fabric_task.py"))
            generation = check.digest(json.dumps(material, sort_keys=True, separators=(",", ":"),
                                                  allow_nan=False).encode())
            directory = self.store / generation
            (directory / "ext").mkdir(parents=True)
            for name, raw in self.source_bytes.items():
                (directory / "ext" / name).write_bytes(raw)
                (directory / "ext" / name).chmod(0o555)
            (directory / "RELEASE.json").write_bytes(encoded(dict(material, digest=generation)))
            (directory / "RELEASE.json").chmod(0o444)
            (directory / "ext").chmod(0o555)
            directory.chmod(0o555)
            generations.append(generation)
        self.patches = contextlib.ExitStack()
        self.patches.enter_context(mock.patch.object(check, "HERE", self.here))
        self.patches.enter_context(mock.patch.object(check, "SOURCES", self.source_hashes))
        self.patches.enter_context(mock.patch.object(check, "GENERATIONS", tuple(generations)))
        self.artifact_hashes = {name: check.digest(raw) for name, raw in self.raw.items()}
        self.patches.enter_context(mock.patch.object(check, "ARTIFACTS", self.artifact_hashes))

    def tearDown(self):
        self.patches.close()
        self.temp.cleanup()

    def artifact(self, name):
        return self.state / (check.RUN + "." + name)

    def qualify(self):
        return check.check_original(check.RUN, check.ROOT)

    def test_positive_is_read_only_and_grants_no_runtime_authority(self):
        def snapshot():
            return {str(p.relative_to(self.base)): (p.read_bytes(), check.identity(p.lstat()))
                    for p in self.base.rglob("*") if p.is_file()}
        before = snapshot()
        with mock.patch("subprocess.run", side_effect=AssertionError("no process")), \
             mock.patch("subprocess.Popen", side_effect=AssertionError("no process")):
            result = self.qualify()
        self.assertEqual(before, snapshot())
        self.assertEqual(result["predicate"], "QUALIFIED_PRELEASE_WORKER_ABSENCE")
        for field in ("canonical_state_changed", "reconciliation_performed", "retry_allowed",
                      "acceptance_eligible", "review_result_available",
                      "telemetry_transport_absence_claimed", "original_selected_generation_recorded"):
            self.assertIs(result[field], False)

    def test_wrong_request_or_root_including_transport_failure_is_refused(self):
        for run, root in [
            ("news-1665-73eefe48-source-review-20261021", check.ROOT),
            (check.RUN, "wrong-root"), (check.RUN, None),
        ]:
            with self.subTest(run=run, root=root), self.assertRaises(check.Unqualified):
                check.check_original(run, root)

    def test_missing_or_extra_execution_artifact_is_refused(self):
        p = self.artifact("request.json")
        saved = p.read_bytes()
        p.unlink()
        with self.assertRaises(check.Unqualified):
            self.qualify()
        p.write_bytes(saved)
        p.chmod(0o600)
        self.artifact("result").write_bytes(b"unexpected worker result")
        with self.assertRaises(check.Unqualified):
            self.qualify()

    def test_changed_bytes_even_relinked_as_a_consistent_chain_are_refused(self):
        p = self.artifact("request.json")
        value = json.loads(p.read_bytes())
        value["root_id"] = "rewritten"
        p.write_bytes(encoded(value))
        with self.assertRaisesRegex(check.Unqualified, "historical_artifact_digest"):
            self.qualify()

    def test_private_file_custody_rejects_public_hardlink_symlink_fifo_and_oversize(self):
        p = self.artifact("request.json")
        saved = p.read_bytes()
        for case in ("public", "hardlink", "symlink", "fifo", "oversize"):
            with self.subTest(case=case):
                p.unlink()
                p.write_bytes(saved)
                p.chmod(0o600)
                peer = self.base / ("peer-" + case)
                if case == "public":
                    p.chmod(0o644)
                elif case == "hardlink":
                    os.link(p, peer)
                elif case == "symlink":
                    p.rename(peer)
                    p.symlink_to(peer)
                elif case == "fifo":
                    p.unlink()
                    os.mkfifo(p, 0o600)
                else:
                    p.write_bytes(b"x" * 32769)
                with self.assertRaises((OSError, check.Unqualified)):
                    self.qualify()

    def test_symlinked_parent_is_refused(self):
        original = self.here / "state"
        other = self.here / "saved-state"
        original.rename(other)
        original.symlink_to(other, target_is_directory=True)
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

    def test_additional_artifact_after_chain_validation_is_refused(self):
        real = check.validate_chain
        def racing(raw):
            real(raw)
            self.artifact("prelease.json").write_bytes(b"{}")
        with mock.patch.object(check, "validate_chain", racing):
            with self.assertRaises(check.Unqualified):
                self.qualify()

    def test_historical_manifest_and_source_bytes_are_both_required(self):
        generation = self.store / check.GENERATIONS[0]
        source = generation / "ext/remote_sub.sh"
        original = source.read_bytes()
        source.chmod(0o755)
        source.write_bytes(original + b"changed")
        source.chmod(0o555)
        with self.assertRaisesRegex(check.Unqualified, "historical_source_bytes"):
            self.qualify()
        source.chmod(0o755)
        source.write_bytes(original)
        source.chmod(0o555)
        manifest = generation / "RELEASE.json"
        value = json.loads(manifest.read_bytes())
        value["links"]["unreviewed"] = "alias"
        manifest.chmod(0o644)
        manifest.write_bytes(encoded(value))
        manifest.chmod(0o444)
        with self.assertRaisesRegex(check.Unqualified, "historical_generation_digest"):
            self.qualify()

    def test_late_source_replacement_does_not_escape_final_revalidation(self):
        target = self.store / check.GENERATIONS[0] / "ext/remote_sub.sh"
        real = check.EvidenceReadSet.read
        last = self.store / check.GENERATIONS[-1] / "ext/fabric_continuation.py"
        def racing(reader, path, **kwargs):
            data = real(reader, path, **kwargs)
            if Path(path) == last:
                target.chmod(0o755)
                target.write_bytes(target.read_bytes() + b"changed late")
                target.chmod(0o555)
            return data
        with mock.patch.object(check.EvidenceReadSet, "read", racing):
            with self.assertRaisesRegex(check.Unqualified, "evidence_changed"):
                self.qualify()

    def test_late_generation_directory_permission_change_is_refused(self):
        target = self.store / check.GENERATIONS[0] / "ext"
        real = check.EvidenceReadSet.read
        last = self.store / check.GENERATIONS[-1] / "ext/fabric_continuation.py"
        def racing(reader, path, **kwargs):
            data = real(reader, path, **kwargs)
            if Path(path) == last:
                target.chmod(0o755)
            return data
        with mock.patch.object(check.EvidenceReadSet, "read", racing):
            with self.assertRaises(check.Unqualified):
                self.qualify()

    def test_semantic_false_proofs_fail_even_when_unit_allowlist_is_rebound(self):
        mutations = [
            ("request.json", "root_id", None),
            ("request.json", "parent_run_id", ""),
            ("request.json", "packet_bytes", True),
            ("request.json", "automatic_background_execution", True),
            ("request-launch.json", "state", "LAUNCHED"),
            ("request-launch.json", "route", {"HOST": "auto"}),
            ("request-launch.json", "native_sources", {}),
            ("request-return.json", "controller_rc", True),
            ("request-return.json", "prelease_sha256", "a" * 64),
            ("continuation-request.json", "max_attempts", True),
            ("continuation-finished.json", "effective_run_id", "successor"),
            ("routing-process.jsonl", "returncode", True),
            ("routing-process.jsonl", "timed_out", True),
            ("routing-process.jsonl", "cleanup", {"census_proven": False}),
        ]
        for suffix, key, value in mutations:
            with self.subTest(suffix=suffix, key=key):
                changed = dict(self.raw)
                record = json.loads(changed[suffix])
                record[key] = value
                changed[suffix] = encoded(record)
                with self.assertRaises(check.Unqualified):
                    check.validate_chain(changed)

    def test_duplicate_keys_and_nonfinite_json_are_rejected(self):
        for raw in (b'{"root_id":"one","root_id":"two"}', b'{"value":NaN}'):
            with self.assertRaises(check.Unqualified):
                check.strict_json(raw)

    def test_reconciliation_requires_exact_fresh_proof_before_writing(self):
        import native_plain_packet_reconcile as reconcile
        self.assertFalse(reconcile.receipt_path().exists())
        for bad in ("0" * 64, "", None, True):
            with self.subTest(bad=bad), self.assertRaises(check.Unqualified):
                reconcile.reconcile_original(check.RUN, check.ROOT, bad)
        self.assertFalse(reconcile.receipt_path().exists())

    def test_recorded_disposition_preserves_failure_and_rejects_accept_or_continuation(self):
        import native_plain_packet_reconcile as reconcile
        import fabric_task
        import fabric_continuation
        proof = self.qualify()
        original = {name: (self.artifact(name).read_bytes(), check.identity(self.artifact(name).lstat()))
                    for name in self.raw}
        with mock.patch("subprocess.run", side_effect=AssertionError("no dispatch")):
            result = reconcile.reconcile_original(check.RUN, check.ROOT, proof["proof_sha256"])
        self.assertEqual(result["action"], "RECORDED")
        self.assertIs(result["worker_dispatch_performed"], False)
        self.assertEqual(original, {
            name: (self.artifact(name).read_bytes(), check.identity(self.artifact(name).lstat()))
            for name in self.raw})
        with mock.patch.object(fabric_task, "HERE", self.here):
            status = fabric_task.inspect_run(check.RUN)
            followed = fabric_continuation.resolve(fabric_task, check.RUN)
            with self.assertRaisesRegex(ValueError, "continuation_predecessor_not_qualified"):
                fabric_continuation.eligible(fabric_task, self.here, check.RUN, check.ROOT, check.ROOT)
            with mock.patch("subprocess.run", side_effect=AssertionError("no acceptance")), \
                 contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(fabric_task.main(["accept", check.RUN, "--by", "reviewer"]), 75)
            with mock.patch.object(fabric_task, "_route_with_deadline", side_effect=AssertionError("no route")):
                with self.assertRaisesRegex(fabric_task.FabricTaskError, "REQUEST_RUN_ALREADY_EXISTS"):
                    fabric_task.request(check.RUN, "review", cwd="~", packet=None, stdin_bytes=b"replacement",
                                        root_id=check.ROOT, parent_run_id=check.ROOT)
        self.assertEqual((status["state"], status["rc"], status["signal"]),
                         ("TERMINAL_FAILURE", 78, "prelaunch_failure"))
        self.assertEqual((status["root_id"], status["parent_run_id"]), (check.ROOT, check.ROOT))
        self.assertIs(status["execution_absence_proven"], True)
        self.assertIs(status["result_available"], False)
        self.assertIsNone(status["accepted"])
        self.assertEqual(status["acceptance_state"], "UNVERIFIED")
        self.assertIs(status["same_run_replay_allowed"], False)
        self.assertIs(status["retry_allowed"], False)
        self.assertEqual(followed["effective_run_id"], check.RUN)
        self.assertEqual(followed["prior_attempts"], [])
        self.assertEqual(followed["controller_reason"], "continuation_evidence_unqualified")

    def test_identical_existing_receipt_is_read_only(self):
        import native_plain_packet_reconcile as reconcile
        proof = self.qualify()
        reconcile.reconcile_original(check.RUN, check.ROOT, proof["proof_sha256"])
        p = reconcile.receipt_path()
        before = (p.read_bytes(), check.identity(p.lstat()))
        real_open = os.open
        def no_write(path, flags, *args, **kwargs):
            if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
                raise AssertionError("existing receipt must not be reopened for writing")
            return real_open(path, flags, *args, **kwargs)
        with mock.patch("os.open", no_write):
            result = reconcile.reconcile_original(check.RUN, check.ROOT, proof["proof_sha256"])
        self.assertEqual(result["action"], "ALREADY_RECORDED")
        self.assertEqual(before, (p.read_bytes(), check.identity(p.lstat())))

    def test_partial_receipt_is_preserved_and_never_repairs_itself(self):
        import native_plain_packet_reconcile as reconcile
        import fabric_task
        proof = self.qualify()
        p = reconcile.receipt_path()
        p.write_bytes(b'{"schema":')
        p.chmod(0o600)
        before = (p.read_bytes(), check.identity(p.lstat()))
        with self.assertRaises(check.Unqualified):
            reconcile.reconcile_original(check.RUN, check.ROOT, proof["proof_sha256"])
        self.assertEqual(before, (p.read_bytes(), check.identity(p.lstat())))
        with mock.patch.object(fabric_task, "HERE", self.here):
            status = fabric_task.inspect_run(check.RUN)
        self.assertEqual(status["state"], "STATUS_UNREADABLE")
        self.assertIsNone(status["root_id"])
        self.assertIsNone(status["accepted"])

    def test_interrupted_receipt_write_keeps_partial_artifact_unqualified(self):
        import native_plain_packet_reconcile as reconcile
        proof = self.qualify()
        real_write = os.write
        calls = 0
        def interrupted(fd, data):
            nonlocal calls
            calls += 1
            if calls == 1:
                return real_write(fd, data[:17])
            raise OSError("injected publication interruption")
        with mock.patch("os.write", interrupted), self.assertRaises(reconcile.PublicationUnqualified):
            reconcile.reconcile_original(check.RUN, check.ROOT, proof["proof_sha256"])
        p = reconcile.receipt_path()
        self.assertEqual(p.stat().st_size, 17)
        self.assertEqual(p.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(check.Unqualified):
            reconcile.status_from_receipt()
        before = p.read_bytes()
        with self.assertRaises(check.Unqualified):
            reconcile.reconcile_original(check.RUN, check.ROOT, proof["proof_sha256"])
        self.assertEqual(p.read_bytes(), before)

    def test_existing_receipt_symlink_never_overwrites_target(self):
        import native_plain_packet_reconcile as reconcile
        proof = self.qualify()
        target = self.base / "unrelated"
        target.write_bytes(b"must stay unchanged")
        reconcile.receipt_path().symlink_to(target)
        with self.assertRaises((OSError, check.Unqualified)):
            reconcile.reconcile_original(check.RUN, check.ROOT, proof["proof_sha256"])
        self.assertEqual(target.read_bytes(), b"must stay unchanged")

    def test_result_appearance_invalidates_proof_and_recorded_status(self):
        import native_plain_packet_reconcile as reconcile
        proof = self.qualify()
        reconcile.reconcile_original(check.RUN, check.ROOT, proof["proof_sha256"])
        result = self.here / "lanes" / (check.RUN + ".remote.stdout")
        result.write_bytes(b"contradictory result")
        result.chmod(0o600)
        with self.assertRaisesRegex(check.Unqualified, "contradictory_original_result"):
            reconcile.status_from_receipt()

    def test_same_byte_receipt_replacement_before_readback_is_refused(self):
        import native_plain_packet_reconcile as reconcile
        proof = self.qualify()
        real_read = reconcile.read_receipt
        def replaced(held, current_proof):
            p = reconcile.receipt_path()
            other = self.base / "replacement-receipt"
            other.write_bytes(p.read_bytes())
            other.chmod(0o600)
            os.replace(other, p)
            return real_read(held, current_proof)
        with mock.patch.object(reconcile, "read_receipt", replaced):
            with self.assertRaisesRegex(check.Unqualified, "new_receipt_replaced"):
                reconcile.reconcile_original(check.RUN, check.ROOT, proof["proof_sha256"])
        settled = reconcile.status_from_receipt()
        self.assertEqual(settled["state"], "TERMINAL_FAILURE")
        self.assertIs(settled["retry_allowed"], False)

    def test_complete_write_with_fsync_error_is_settled_only_by_fresh_readback(self):
        import native_plain_packet_reconcile as reconcile
        proof = self.qualify()
        with mock.patch("os.fsync", side_effect=OSError("injected fsync failure")):
            with self.assertRaises(reconcile.PublicationUnqualified) as failure:
                reconcile.reconcile_original(check.RUN, check.ROOT, proof["proof_sha256"])
        self.assertEqual(failure.exception.effect_state, "EFFECT_UNKNOWN")
        # The modifying call is unqualified, not evidence of NOT_APPLIED.
        # A complete receipt can subsequently be reconciled without rewriting it.
        p = reconcile.receipt_path()
        before = (p.read_bytes(), check.identity(p.lstat()))
        status = reconcile.status_from_receipt()
        self.assertEqual(status["state"], "TERMINAL_FAILURE")
        self.assertIs(status["retry_allowed"], False)
        self.assertIs(status["result_available"], False)
        self.assertEqual(before, (p.read_bytes(), check.identity(p.lstat())))

    def test_context_cleanup_failure_after_publication_remains_effect_unknown(self):
        import native_plain_packet_reconcile as reconcile
        proof = self.qualify()
        real_exit = check.EvidenceReadSet.__exit__
        def failed_exit(held, *args):
            real_exit(held, *args)
            raise OSError("injected retained-descriptor cleanup failure")
        with mock.patch.object(check.EvidenceReadSet, "__exit__", failed_exit):
            with self.assertRaises(reconcile.PublicationUnqualified) as failure:
                reconcile.reconcile_original(check.RUN, check.ROOT, proof["proof_sha256"])
        self.assertEqual(failure.exception.effect_state, "EFFECT_UNKNOWN")
        status = reconcile.status_from_receipt()
        self.assertEqual(status["state"], "TERMINAL_FAILURE")
        self.assertIs(status["retry_allowed"], False)

    def test_cli_output_failure_after_publication_never_claims_not_applied(self):
        import native_plain_packet_reconcile as reconcile
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
            rc = fabric_task.main(["reconcile-plain-packet-retention", check.RUN,
                "--root", check.ROOT, "--expected-proof-sha256", proof["proof_sha256"]])
        self.assertEqual(rc, 78)
        self.assertNotIn("NOT_APPLIED", stdout.getvalue() + stderr.getvalue())
        self.assertIn("EFFECT_UNKNOWN", stderr.getvalue())
        self.assertEqual(calls, 1)
        status = reconcile.status_from_receipt()
        self.assertEqual(status["state"], "TERMINAL_FAILURE")
        self.assertIs(status["retry_allowed"], False)

    def test_evidence_change_after_creation_never_reports_reconciled(self):
        import native_plain_packet_reconcile as reconcile
        proof = self.qualify()
        real_open = os.open
        def changed(path, flags, *args, **kwargs):
            fd = real_open(path, flags, *args, **kwargs)
            if flags & os.O_CREAT and path == reconcile.receipt_path().name:
                self.artifact("request.json").write_bytes(b"changed during publication")
            return fd
        with mock.patch("os.open", changed):
            with self.assertRaisesRegex(check.Unqualified, "evidence_changed"):
                reconcile.reconcile_original(check.RUN, check.ROOT, proof["proof_sha256"])
        self.assertTrue(reconcile.receipt_path().exists())
        with self.assertRaises(check.Unqualified):
            reconcile.status_from_receipt()

    def test_unsafe_record_types_and_unknown_fields_are_not_projected(self):
        import native_plain_packet_reconcile as reconcile
        proof = self.qualify()
        reconcile.reconcile_original(check.RUN, check.ROOT, proof["proof_sha256"])
        p = reconcile.receipt_path()
        original = json.loads(p.read_bytes())
        for key, value in (("controller_rc", True), ("retry_allowed", True),
                           ("unexpected_authority", True), ("root_id", "replacement-root")):
            with self.subTest(key=key):
                row = dict(original)
                row[key] = value
                p.write_bytes(reconcile.canonical(row))
                with self.assertRaises(check.Unqualified):
                    reconcile.status_from_receipt()

    def test_reconciliation_cli_distinguishes_refusal_from_ambiguous_publication(self):
        import native_plain_packet_reconcile as reconcile
        import fabric_task
        cases = [(check.Unqualified("proof mismatch"), "NOT_APPLIED"),
                 (reconcile.PublicationUnqualified("interrupted"), "EFFECT_UNKNOWN")]
        for error, expected in cases:
            with self.subTest(expected=expected):
                with mock.patch.object(reconcile, "reconcile_original", side_effect=error), \
                     contextlib.redirect_stdout(io.StringIO()) as stdout, \
                     contextlib.redirect_stderr(io.StringIO()):
                    rc = fabric_task.main(["reconcile-plain-packet-retention", check.RUN,
                        "--root", check.ROOT, "--expected-proof-sha256", "a" * 64])
                self.assertEqual(rc, 78)
                response = json.loads(stdout.getvalue())
                self.assertEqual(response["effect_state"], expected)
                self.assertIs(response["retry_allowed"], False)
                self.assertIs(response["worker_dispatch_performed"], False)

    def test_cli_check_does_not_call_request_or_change_status(self):
        import fabric_task
        with mock.patch.object(check, "check_original", return_value={"retry_allowed": False}) as called, \
             mock.patch.object(fabric_task, "request", side_effect=AssertionError("no dispatch")), \
             mock.patch.object(fabric_task, "inspect_run", side_effect=AssertionError("no status override")), \
             mock.patch("subprocess.run", side_effect=AssertionError("no process")), \
             contextlib.redirect_stdout(io.StringIO()) as stdout:
            rc = fabric_task.main(["check-plain-packet-retention", check.RUN, "--root", check.ROOT])
        self.assertEqual(rc, 0)
        called.assert_called_once_with(check.RUN, check.ROOT)
        self.assertEqual(json.loads(stdout.getvalue()), {"retry_allowed": False})


if __name__ == "__main__":
    unittest.main()
