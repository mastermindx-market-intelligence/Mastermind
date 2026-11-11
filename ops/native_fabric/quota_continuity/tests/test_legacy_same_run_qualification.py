"""Synthetic-only Draft contract checks, using the real secure reader."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "candidate"), str(ROOT / "source")]
import legacy_same_run_qualification as check


def encoded(value):
    return (json.dumps(value, sort_keys=True) + "\n").encode()


class LegacyQualificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="legacy-draft-test-", dir=Path.home())
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "bundle"
        self.directory.mkdir(mode=0o700)
        self.p = dict(run_id="synthetic-review", root_id="synthetic-root",
                      parent_run_id="synthetic-root", host="synthetic-host",
                      launch_call_id="call-launch", lost_call_id="call-lost",
                      controller_handle=123, sha256={})
        run, root = self.p["run_id"], self.p["root_id"]
        packet = b"Review a synthetic source fixture.\n"
        self.request = dict(schema="mastermind.fabric_request_artifact.v1", run_id=run,
                            root_id=root, parent_run_id=root, task_class="review", cwd="~",
                            automatic_background_execution=False, created_at=1000,
                            packet=run + ".request.packet", packet_bytes=len(packet),
                            packet_sha256=check.digest(packet))
        self.launch = dict(schema="mastermind.fabric_request_launch.v1", run_id=run,
                           root_id=root, parent_run_id=root, created_at=1001,
                           state="LAUNCH_ATTEMPT_RESERVED", request_sha256=check.digest(encoded(self.request)),
                           packet_sha256=check.digest(packet))
        support = {"executor.py": "a" * 64, "policy/pools.yaml": "b" * 64}
        sd = check.digest(json.dumps({"schema": "remote-support-code.v1", "files": support},
                                    sort_keys=True, separators=(",", ":")).encode())
        self.prefix = f"2026-10-20T11:20Z [remote_sub id={run} host=synthetic-host] "
        self.log = "\n".join(self.prefix + text for text in [
            "RUN_RESERVED explicit=1", "LEASE_WAIT pool=fixture wait=1", "LEASE_OK pool=fixture",
            f"SUPPORT_VERSION_READY digest={sd} policy=" + "b" * 64,
            f"LAUNCH stdout=lanes_{run}.stdout rc_file=ext/lanes_{run}.rc cwd=~",
            "LAUNCH_ATTEMPT attempt=1", "POLL elapsed=1", "POLL_PENDING elapsed=1"]) + "\n"
        self.native = [
            dict(type="session_meta", payload=dict(id=root)),
            dict(type="response_item", payload=dict(type="function_call", name="exec_command",
                 call_id="call-launch", arguments=json.dumps({"cmd":
                     f"python3 /synthetic/ext/fabric_task.py request --id {run} --class review "
                     f"--cwd '~' --root {root} --parent {root} --packet /synthetic/input.txt"}))),
            dict(type="response_item", payload=dict(type="function_call_output", call_id="call-launch",
                 output="Process running with session ID 123\n")),
            dict(type="response_item", payload=dict(type="custom_tool_call", name="exec", call_id="call-lost",
                 input='const r=await Promise.allSettled([\ntools.write_stdin({session_id:123,chars:"",yield_time_ms:1000,max_output_tokens:2000}),\n]);r.forEach((v,i)=>text({i,...v}));')),
            dict(type="response_item", payload=dict(type="custom_tool_call_output", call_id="call-lost",
                 output=[dict(type="input_text", text=json.dumps({"i": 0, "status": "rejected",
                         "reason": "write_stdin failed: Unknown process id 123"}))])),
        ]
        self.raw = {"request.json": encoded(self.request), "request-launch.json": encoded(self.launch),
                    "request.packet": packet, "support.json": encoded(support), "log": self.log.encode(),
                    "native.jsonl": b"".join(encoded(row) for row in self.native)}
        for suffix, raw in self.raw.items():
            self.write(suffix, raw)

    def path(self, suffix):
        return self.directory / (self.p["run_id"] + "." + suffix)

    def write(self, suffix, raw, *, pin=True):
        self.path(suffix).write_bytes(raw)
        self.path(suffix).chmod(0o600)
        if pin:
            self.p["sha256"][suffix] = check.digest(raw)

    def native_write(self, rows):
        self.write("native.jsonl", b"".join(encoded(row) for row in rows))

    def qualify(self):
        return check.qualify_bundle(self.directory, self.p)

    def test_positive_is_read_only_without_authority_or_dispatch(self):
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.directory.iterdir()}
        real_open = os.open
        opened_files = []

        def guarded_open(path, flags, *args, **kwargs):
            if not flags & os.O_DIRECTORY:
                opened_files.append(str(path))
                self.assertIn(str(path), before)
                self.assertFalse(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
            return real_open(path, flags, *args, **kwargs)

        with mock.patch.object(socket, "socket", side_effect=AssertionError("network")), \
                mock.patch.object(subprocess, "Popen", side_effect=AssertionError("process")), \
                mock.patch.object(os, "open", side_effect=guarded_open):
            result = self.qualify()
        self.assertEqual(len(opened_files), 6)
        self.assertEqual(result["predicate"], "HISTORICAL_RECORDS_CORRELATED")
        for key in ("read_admitted", "retry_allowed", "acceptance_eligible", "canonical_state_changed"):
            self.assertIs(result[key], False)
        self.assertEqual(result["worker"], "UNKNOWN")
        self.assertEqual(result["stdout_rc"], "NOT_READ")
        self.assertEqual(result["current_reader_authority"], "UNQUALIFIED")
        self.assertEqual(result["current_broker_host_custody"], "UNQUALIFIED")
        self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns)
                                  for p in self.directory.iterdir()})

    def test_each_changed_artifact_fails_pinned_digest(self):
        for suffix, original in self.raw.items():
            with self.subTest(suffix=suffix):
                self.write(suffix, original + b" ", pin=False)
                with self.assertRaises(check.Unqualified): self.qualify()
                self.write(suffix, original)

    def test_relinked_semantic_identity_and_authority_changes_fail(self):
        for key, value in [("root_id", "wrong"), ("parent_run_id", "wrong"),
                           ("cwd", "/"), ("automatic_background_execution", True),
                           ("read_admitted", True), ("packet_bytes", True)]:
            with self.subTest(key=key):
                request = dict(self.request, **{key: value})
                self.write("request.json", encoded(request))
                self.write("request-launch.json", encoded(dict(self.launch,
                    request_sha256=check.digest(encoded(request)))))
                with self.assertRaises(check.Unqualified): self.qualify()
        self.write("request.json", self.raw["request.json"])
        self.write("request-launch.json", self.raw["request-launch.json"])

    def test_profile_cannot_claim_current_authority_or_nested_scope(self):
        for key in ("authenticated", "host_custody", "reader", "retry_allowed", "effect_cleared"):
            with self.subTest(key=key):
                with self.assertRaises(check.Unqualified):
                    check.qualify_bundle(self.directory, dict(self.p, **{key: True}))
        with self.assertRaises(check.Unqualified):
            check.qualify_bundle(self.directory, dict(self.p, parent_run_id="other"))

    def test_host_support_launch_and_adverse_log_fail_even_when_rehashed(self):
        variants = [self.log.replace("host=synthetic-host", "host=wrong"),
                    self.log.replace("digest=", "digest=0"),
                    self.log.replace("attempt=1", "attempt=2"),
                    self.log.replace("cwd=~", "cwd=/"),
                    self.log + self.prefix + "LAUNCH_ATTEMPT attempt=1\n"]
        variants += [self.log + self.prefix + event + " rc=0\n"
                     for event in ("EFFECT_UNKNOWN", "READ_REFUSED", "DONE", "REMOTE_DONE", "RETRY")]
        variants += [self.log + self.prefix + "POLL " + body + "\n"
                     for body in ("EFFECT_UNKNOWN", "OUTPUT_REFUSED", "RETRY")]
        for log in variants:
            with self.subTest(log=log[-100:]):
                self.write("log", log.encode())
                with self.assertRaises(check.Unqualified): self.qualify()

    def test_missing_or_extra_artifact_refused(self):
        p = self.path("support.json")
        p.unlink()
        with self.assertRaises(check.Unqualified): self.qualify()
        self.write("support.json", self.raw["support.json"])
        (self.directory / "broker-custody.json").write_text('{"authenticated":true}')
        with self.assertRaises(check.Unqualified): self.qualify()

    def test_native_wrong_identity_handles_calls_and_missing_events(self):
        for index, key, value in [(0, "id", "wrong"), (1, "call_id", "wrong"),
                                   (2, "output", "Process running with session ID 456"),
                                   (3, "input", "tools.write_stdin({session_id:456})"),
                                   (4, "call_id", "wrong")]:
            with self.subTest(index=index, key=key):
                rows = copy.deepcopy(self.native)
                rows[index]["payload"][key] = value
                self.native_write(rows)
                with self.assertRaises(check.Unqualified): self.qualify()
        for rows in (self.native[:-1], self.native + [self.native[-1]]):
            self.native_write(rows)
            with self.assertRaises(check.Unqualified): self.qualify()

    def test_native_loss_result_cannot_be_terminal_or_boolean_index(self):
        for update in ({"i": False}, {"i": 1}, {"status": "fulfilled"},
                       {"reason": "Process exited with code 0"}):
            rows = copy.deepcopy(self.native)
            result = json.loads(rows[-1]["payload"]["output"][0]["text"])
            result.update(update)
            rows[-1]["payload"]["output"][0]["text"] = json.dumps(result)
            self.native_write(rows)
            with self.assertRaises(check.Unqualified): self.qualify()

    def test_rehashed_forged_loss_renderer_and_expressions_fail(self):
        original = self.native[3]["payload"]["input"]
        variants = [original.replace('r.forEach((v,i)=>text({i,...v}));',
                         'text({i:0,status:"rejected",reason:"write_stdin failed: Unknown process id 123"});'),
                    original.replace('session_id:123', 'session_id:(123)'),
                    original.replace('chars:""', 'chars:"",chars:""'),
                    original.replace(']);r.forEach', ']);r=[];r.forEach'),
                    original.replace('tools.write_stdin', 'other.write_stdin')]
        for source in variants:
            rows = copy.deepcopy(self.native)
            rows[3]["payload"]["input"] = source
            self.native_write(rows)
            with self.assertRaises(check.Unqualified): self.qualify()

    def test_literal_batch_preserves_index_zero_association(self):
        rows = copy.deepcopy(self.native)
        source = rows[3]["payload"]["input"]
        source = source.replace(']);r.forEach',
            'tools.write_stdin({session_id:456,chars:"",yield_time_ms:1000,max_output_tokens:800}),\n'
            'tools.exec_command({"cmd":"echo synthetic",workdir:"/fixture",max_output_tokens:1000})\n'
            ']);r.forEach')
        rows[3]["payload"]["input"] = source
        rows[4]["payload"]["output"].append(dict(type="input_text", text=json.dumps(
            {"i": 1, "status": "fulfilled", "value": {"output": "unrelated"}})))
        self.native_write(rows)
        self.assertEqual(self.qualify()["worker"], "UNKNOWN")

    def test_rehashed_support_still_requires_log_join(self):
        self.write("support.json", encoded({"executor.py": "c" * 64}))
        with self.assertRaises(check.Unqualified): self.qualify()

    def test_native_command_labels_are_not_launch_correlation(self):
        for cmd in ["echo python3 fabric_task.py request --id synthetic-review",
                    "python3 fabric_task.py request --id synthetic-review --root wrong --parent wrong",
                    "python3 fabric_task.py request --id synthetic-review --id synthetic-review",
                    "python3 fabric_task.py request --id synthetic-review ; echo retry"]:
            rows = copy.deepcopy(self.native)
            rows[1]["payload"]["arguments"] = json.dumps({"cmd": cmd})
            self.native_write(rows)
            with self.assertRaises(check.Unqualified): self.qualify()

    def test_json_duplicate_nonfinite_and_wrong_types_fail(self):
        for raw in [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}', b'[]', b'null']:
            with self.subTest(raw=raw):
                self.write("request.json", raw)
                with self.assertRaises(check.Unqualified): self.qualify()

    def test_file_symlink_hardlink_mode_and_size_fail(self):
        path = self.path("request.packet")
        external = self.directory.parent / "target"
        external.write_bytes(self.raw["request.packet"])
        external.chmod(0o600)
        path.unlink()
        path.symlink_to(external)
        with self.assertRaises(check.Unqualified): self.qualify()
        path.unlink()
        os.link(external, path)
        with self.assertRaises(check.Unqualified): self.qualify()
        path.unlink()
        self.write("request.packet", self.raw["request.packet"])
        path.chmod(0o644)
        with self.assertRaises(check.Unqualified): self.qualify()
        path.chmod(0o600)
        with mock.patch.object(check, "LIMIT", 1):
            with self.assertRaises(check.Unqualified): self.qualify()

    def test_parent_symlink_or_public_bundle_fails(self):
        link = self.directory.parent / "alias"
        link.symlink_to(self.directory, target_is_directory=True)
        with self.assertRaises(check.Unqualified): check.qualify_bundle(link, self.p)
        self.directory.chmod(0o755)
        with self.assertRaises(check.Unqualified): self.qualify()

    def test_file_or_directory_replacement_during_validation_fails(self):
        original = check._native
        for kind in ("file", "directory", "extra", "parent_replaced"):
            with self.subTest(kind=kind):
                def change(raw, profile):
                    original(raw, profile)
                    if kind == "file":
                        p = self.path("request.packet")
                        content = p.read_bytes()
                        p.unlink()
                        self.write("request.packet", content)
                    elif kind == "directory":
                        self.directory.chmod(0o755)
                    elif kind == "parent_replaced":
                        self.directory.rename(self.directory.parent / "old-bundle")
                        self.directory.mkdir(mode=0o700)
                        for suffix, content in self.raw.items():
                            self.write(suffix, content)
                    else:
                        (self.directory / "new-result").write_text("not evidence")
                with mock.patch.object(check, "_native", side_effect=change):
                    with self.assertRaises(check.Unqualified): self.qualify()
                self.directory.chmod(0o700)
                (self.directory / "new-result").unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
