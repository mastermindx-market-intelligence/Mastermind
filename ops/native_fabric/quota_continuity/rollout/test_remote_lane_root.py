#!/usr/bin/env python3
"""Inert proof for registry-bound physical roots; no network/provider effects."""
from __future__ import annotations
import base64
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time
import types
import unittest
from unittest import mock
import test_plain_original_delivery as plain
from test_plain_original_delivery import (
    ALIAS, CAND, HOST, MODEL, PACKET, PARENT, POLICY, ROOT, RUN_ID, SRC, STDOUT,
    exclusive, sha,
)


def token(value):
    return base64.urlsafe_b64encode(json.dumps(
        value, sort_keys=True, separators=(",", ":")).encode()).decode()


def replace_private(path, data, mode=0o600):
    if os.path.lexists(path):
        path.unlink()
    exclusive(path, data, mode)


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def shell_function(source, name):
    body = source.split(name + "() {\n", 1)[1].split("\n}\n", 1)[0]
    return name + "() {\n" + body + "\n}\n"


class PhysicalRootCase(unittest.TestCase):
    post_launch = plain.PlainRepairCase.post_launch
    collect = plain.PlainRepairCase.collect
    receipt_on_disk = plain.PlainRepairCase.receipt_on_disk

    def setUp(self):
        plain.PlainRepairCase.setUp(self)
        self.original_path = list(sys.path)
        for directory in (SRC, CAND):
            sys.path.insert(1, str(directory))
        self.delivery = self.collector.delivery
        self.shell = (CAND / "remote_sub.sh").read_text()
        self.physical = Path(self._stack.name) / "admitted" / "lanes"
        self.physical.parent.mkdir(mode=0o700)
        (self.fx.home / "lanes").rename(self.physical)
        (self.fx.home / "lanes").symlink_to(self.physical, target_is_directory=True)
        for relative in ("ext/active", "orch/fabric"):
            (self.physical / relative).mkdir(parents=True, mode=0o700)
        self.entry = {"allowed_modes": ["glm", "qwen", "grok", "glm-codex"],
                      "ssh_alias": ALIAS, "cores": 8, "max_active": 2,
                      "load_gate": 8, "physical_lane_root": str(self.physical)}
        self.write_registry(self.entry)
        self.binding = self.delivery.configured_remote_lane_root(HOST, self.entry)
        self.layout = self.delivery.observe_remote_lane_layout(self.binding)
        self.layout_token = token(self.layout)
        self.publisher = module_at("inert_physical_publisher", CAND / "support_bundle.py")
        self.source = Path(self._stack.name) / "published-source"
        self.source.mkdir(mode=0o700)
        policy = (json.dumps({"routing": {}, "pools": {"grok": {"windows": {"weekly": {}}}}})
                  + "\n").encode()
        exclusive(self.physical / "orch/fabric/pools.yaml", policy)
        manifest = {}
        for name in self.publisher.PHYSICAL_ROOT_SOURCE_FILES:
            source = CAND / name
            if not source.exists():
                source = SRC / name
            raw = policy if name == "pools.yaml" else source.read_bytes()
            exclusive(self.source / name, raw)
            manifest[name] = sha(raw)
        self.published = self.publisher.publish(self.source, self.physical / "ext", manifest)
        self.fx.support_manifest = manifest
        self.fx.support_digest = self.published.parent.name
        replace_private(self.fx.support_pin, json.dumps(
            manifest, sort_keys=True, separators=(",", ":")).encode())
        self.fx.refresh_binding()
        self.executor = module_at("inert_physical_executor", self.published / "remote_sub_exec.py")

    def tearDown(self):
        # Only owned sealed fixtures; do not follow state aliases.
        for walked, directories, files in os.walk(self._stack.name, followlinks=False):
            os.chmod(walked, 0o700)
        sys.path[:] = self.original_path
        plain.PlainRepairCase.tearDown(self)

    def write_registry(self, entry):
        replace_private(self.fx.ctl / "hosts.json", json.dumps({HOST: entry}).encode())

    def executor_environment(self):
        return {"REMOTE_SUB_LANE_ROOT_LAYOUT": self.layout_token,
                "REMOTE_SUB_LANE_PACKET_SHA256": sha(PACKET),
                "SUPPORT_DIGEST": self.fx.support_digest,
                "LANE_REMOTE_HOST": HOST, "POOL_ORCHESTRATOR_ID": ROOT,
                "POOL_PARENT_RUN_ID": PARENT, "REMOTE_SUB_RUN_ID": RUN_ID,
                "PATH": os.environ.get("PATH", "")}

    def guard(self, *, mode="glm", env=None):
        return self.executor._bound_lane_packet(
            RUN_ID, mode, self.physical / "tmp" / (RUN_ID + ".txt"), "~",
            self.published, self.executor_environment() if env is None else env)

    def transport_reader(self):
        source = self.shell.split("<<'PY_VERIFY_PLAIN_TRANSPORT'\n", 1)[1].split(
            "\nPY_VERIFY_PLAIN_TRANSPORT", 1)[0]
        source = source.replace("$PLAIN_TRANSPORT_CHAIN_SOURCE",
                                self.delivery.remote_directory_chain_source())
        prefix = ("import pwd, types, sys\n"
                  f"pwd.getpwuid=lambda uid: types.SimpleNamespace(pw_dir={str(self.fx.home)!r})\n"
                  f"sys.argv={['reader', RUN_ID, self.fx.support_digest, POLICY, self.layout_token]!r}\n")
        return subprocess.run([sys.executable, "-I", "-S", "-c", prefix + source],
                              capture_output=True, text=True, timeout=15)

    def verify_transport(self, observation=None):
        if not self.fx.log_path.exists():
            exclusive(self.fx.log_path, self.fx.prelaunch_log().encode())
        if observation is None:
            result = self.transport_reader()
            self.assertEqual(result.returncode, 0, result.stderr)
            observation = json.loads(result.stdout)
        seen = self.fx.ctl / "observation.json"
        replace_private(seen, json.dumps(observation, sort_keys=True,
                                        separators=(",", ":")).encode())
        return self.fx.run_helper([
            "transport-verify", str(self.fx.log_path), str(self.fx.receipt_path),
            str(self.fx.packet_pin), str(self.fx.lease_path), str(seen), RUN_ID,
            HOST, "glm", MODEL, self.fx.support_digest, POLICY, "0123456789ab",
            ALIAS, self.layout_token])

    def qualified(self):
        result = self.verify_transport()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = self.fx.run_helper([
            "launch-binding", str(self.fx.log_path), str(self.fx.packet_pin),
            str(self.fx.lease_path), RUN_ID, ROOT, PARENT, HOST, "glm", MODEL,
            self.fx.support_digest, "0123456789ab", ALIAS, str(self.fx.receipt_path)])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        row = json.loads(result.stdout)
        self.post_launch()
        self.fx.refresh_binding()
        return row

    def change_generation_link(self, name):
        alias = self.published / name
        decoy = Path(self._stack.name) / ("decoy-" + name)
        decoy.mkdir(mode=0o700)
        self.published.chmod(0o700)
        alias.unlink()
        alias.symlink_to(decoy, target_is_directory=True)
        self.published.chmod(0o555)

    def test_actual_v2_transport_binding_generated_collection_and_readback(self):
        row = self.qualified()
        receipt = self.collect()
        self.assertEqual(receipt["state"], "COMPLETE")
        self.assertTrue(receipt["delivery_verified"])
        self.assertEqual(receipt["acceptance"], "NOT_RECORDED")
        self.assertFalse(receipt["original_operation_mutated"])
        binding = receipt["plain_launch_binding"]
        self.assertEqual(binding["schema"], "mastermind.fabric_plain_launch_binding.v2")
        self.assertEqual(binding["binding_sha256"], row["binding_sha256"])
        self.assertEqual(binding["transport"]["lane_root"], self.layout)
        for flag in ("producer_root_authenticated", "producer_packet_consumption_attested",
                     "served_model_and_historical_physical_host_authenticated"):
            self.assertFalse(receipt["plain_provenance"][flag])
        self.assertEqual(self.receipt_on_disk()[1], STDOUT)

    def test_legacy_home_alias_retarget_does_not_redirect_bound_paths(self):
        decoy = Path(self._stack.name) / "unrelated-home-lanes"
        decoy.mkdir(mode=0o700)
        alias = self.fx.home / "lanes"
        alias.unlink()
        alias.symlink_to(decoy, target_is_directory=True)
        self.assertEqual(self.guard()[1], PACKET)
        self.assertEqual(self.guard(mode="qwen")[1], PACKET)
        self.qualified()
        self.assertEqual(self.collect()["state"], "COMPLETE")
        self.assertEqual(self.receipt_on_disk()[1], STDOUT)
        self.assertEqual(list(decoy.iterdir()), [])

    def test_exact_published_closure_imports_without_source_tree(self):
        self.assertEqual(len(self.publisher.SOURCE_FILES), 37)
        self.assertEqual(len(self.publisher.PHYSICAL_ROOT_SOURCE_FILES), 38)
        self.assertEqual(self.publisher.PHYSICAL_ROOT_SOURCE_FILES,
                         self.publisher.SOURCE_FILES | {"artifact_delivery.py"})
        raw = self.shell.split("SUPPORT_FILES=(\n", 1)[1].split("\n)", 1)[0]
        self.assertEqual(set(raw.split()), self.publisher.SOURCE_FILES)
        code = (f"import sys; sys.path.insert(0, {str(self.published)!r}); "
                "import artifact_delivery, remote_sub_exec; "
                f"assert artifact_delivery.HERE == __import__('pathlib').Path({str(self.published)!r}); "
                "assert callable(remote_sub_exec._bound_lane_packet)")
        result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", code],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        old = {k: v for k, v in self.fx.support_manifest.items()
               if k in self.publisher.SOURCE_FILES}
        prior = self.publisher.publish(self.source, self.physical / "ext", old)
        self.assertNotEqual(prior, self.published)
        self.assertEqual(self.publisher.publish(self.source, self.physical / "ext", old), prior)
        with self.assertRaises(ValueError):
            self.publisher.publish(self.source, self.physical / "ext",
                                   {k: v for k, v in self.fx.support_manifest.items()
                                    if k != "artifact_reader.py"})

    def test_same_path_root_replacement_refuses_matching_bytes(self):
        old = self.physical.with_name("old-lanes")
        self.physical.rename(old)
        shutil.copytree(old, self.physical, symlinks=True)
        with self.assertRaisesRegex(ValueError, "remote_lane_layout_changed"):
            self.guard()
        self.assertNotEqual(self.transport_reader().returncode, 0)

    def test_same_path_required_child_replacement_refuses(self):
        child = self.physical / "tmp"
        child.rename(self.physical / "old-tmp")
        child.mkdir(mode=0o700)
        exclusive(child / (RUN_ID + ".txt"), PACKET)
        with self.assertRaisesRegex(ValueError, "remote_lane_layout_changed"):
            self.guard()

    def test_symlink_required_child_refuses(self):
        child = self.physical / "tmp"
        child.rename(self.physical / "real-tmp")
        child.symlink_to("real-tmp", target_is_directory=True)
        with self.assertRaises((OSError, ValueError)):
            self.guard()
        self.assertNotEqual(self.transport_reader().returncode, 0)

    def test_writable_required_directory_refuses(self):
        (self.physical / "ext/lanes").chmod(0o777)
        with self.assertRaises((OSError, ValueError)):
            self.guard()
        self.assertNotEqual(self.transport_reader().returncode, 0)

    def test_packet_hardlink_symlink_and_group_write_refuse(self):
        path = self.physical / "tmp" / (RUN_ID + ".txt")
        path.chmod(0o660)
        with self.assertRaises(ValueError):
            self.guard()
        path.chmod(0o600)
        other = self.physical / "tmp" / "other.txt"
        os.link(path, other)
        with self.assertRaises(ValueError):
            self.guard()
        self.assertNotEqual(self.transport_reader().returncode, 0)
        path.unlink()
        path.symlink_to(other.name)
        with self.assertRaises((OSError, ValueError)):
            self.guard()
        self.assertNotEqual(self.transport_reader().returncode, 0)

    def test_packet_tamper_refuses_before_admission(self):
        replace_private(self.physical / "tmp" / (RUN_ID + ".txt"), b"changed\n")
        with self.assertRaisesRegex(ValueError, "PACKET_REFUSED"):
            self.guard()
        with mock.patch.object(self.executor.LaneLease, "acquire") as acquire:
            with mock.patch.dict(os.environ, self.executor_environment(), clear=True):
                rc = self.executor._execute(
                    ["remote_sub_exec.py", RUN_ID, "glm",
                     str(self.physical / "tmp" / (RUN_ID + ".txt")), "~", MODEL],
                    {"entered_monotonic_ns": time.monotonic_ns(), "started": False})
        self.assertEqual(rc, 78)
        acquire.assert_not_called()

    def test_code_permissions_links_and_tamper_refuse(self):
        code = self.published / "artifact_reader.py"
        code.chmod(0o755)
        with self.assertRaises(ValueError):
            self.guard()
        code.chmod(0o555)
        hardlink = self.physical / "tmp" / "linked-code.py"
        os.link(code, hardlink)
        with self.assertRaises(ValueError):
            self.guard()
        hardlink.unlink()
        code.chmod(0o755)
        code.write_bytes(code.read_bytes() + b"\n# tampered\n")
        code.chmod(0o555)
        with self.assertRaisesRegex(ValueError, "SUPPORT_REFUSED"):
            self.guard()
        self.assertNotEqual(self.transport_reader().returncode, 0)

    def test_generation_active_link_retarget_refuses_before_admission(self):
        self.change_generation_link("active")
        with mock.patch.object(self.executor.LaneLease, "acquire") as acquire:
            with mock.patch.dict(os.environ, self.executor_environment(), clear=True):
                rc = self.executor._execute(
                    ["remote_sub_exec.py", RUN_ID, "glm",
                     str(self.physical / "tmp" / (RUN_ID + ".txt")), "~", MODEL],
                    {"entered_monotonic_ns": time.monotonic_ns(), "started": False})
        self.assertEqual(rc, 78)
        acquire.assert_not_called()
        self.assertNotEqual(self.transport_reader().returncode, 0)

    def test_generation_lanes_link_retarget_refuses_collection(self):
        self.qualified()
        self.change_generation_link("lanes")
        with self.assertRaises((OSError, ValueError)):
            self.guard()
        with self.assertRaisesRegex(ValueError, "filesystem_refused"):
            self.collect()

    def test_forged_release_link_map_cannot_redirect_owner(self):
        meta_path = self.published.parent / "RELEASE.json"
        meta = json.loads(meta_path.read_bytes())
        meta["links"]["ext/active"] = str(Path(self._stack.name) / "other")
        meta_path.chmod(0o644)
        meta_path.write_text(json.dumps(meta))
        meta_path.chmod(0o444)
        with self.assertRaisesRegex(ValueError, "binding_invalid"):
            self.guard()
        self.assertNotEqual(self.transport_reader().returncode, 0)

    def test_registry_path_or_alias_change_refuses_existing_binding(self):
        self.qualified()
        for field, value in (("physical_lane_root", str(self.physical) + "-different"),
                             ("ssh_alias", "different-host")):
            with self.subTest(field=field):
                self.write_registry(dict(self.entry, **{field: value}))
                result = self.fx.run_helper([
                    "lane-root-current", str(self.fx.ctl / "hosts.json"),
                    HOST, token(self.binding)])
                self.assertNotEqual(result.returncode, 0)
                with self.assertRaisesRegex(ValueError, "registry_changed"):
                    self.collect()
        self.write_registry(self.entry)

    def test_mixed_or_extra_transport_schema_never_retains(self):
        observed = json.loads(self.transport_reader().stdout)
        for row in (dict(observed, schema="mastermind.transport_observation.v1"),
                    {k: v for k, v in observed.items() if k != "lane_root"},
                    dict(observed, extra="unreviewed")):
            with self.subTest(keys=sorted(row)):
                result = self.verify_transport(row)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.fx.receipt_path.exists())
                self.assertNotIn("TRANSPORT_VERIFIED ", self.fx.log_path.read_text())

    def test_closed_root_and_layout_schemas_refuse_unqualified_values(self):
        for path in ("~/lanes", "/tmp/../lanes", "/tmp//lanes",
                     "/tmp/lanes/", "/tmp/space lanes", "/tmp/$(touch-no)"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.delivery.configured_remote_lane_root(
                    HOST, dict(self.entry, physical_lane_root=path))
        for value in (dict(self.layout, extra=1),
                      dict(self.layout, sha256="0" * 64),
                      dict(self.layout, directories={"tmp": [1, 2, 3, 4]})):
            with self.assertRaises(ValueError):
                self.delivery.validate_remote_lane_layout(value)

    def test_executor_uses_bound_packet_and_physical_state_at_worker_boundary(self):
        reached = {}
        class WorkerBoundary(BaseException):
            pass
        class Lease:
            def __enter__(inner):
                return inner
            def __exit__(inner, *args):
                return False
            def hold_for_reconciliation(inner, reason):
                reached["hold"] = reason
        def capture(command, **kwargs):
            reached.update(command=command, kwargs=kwargs)
            raise WorkerBoundary()
        with ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, self.executor_environment(), clear=True))
            acquire = stack.enter_context(mock.patch.object(
                self.executor.LaneLease, "acquire", return_value=Lease()))
            stack.enter_context(mock.patch.object(self.executor, "install_signal_cleanup"))
            stack.enter_context(mock.patch.object(self.executor, "load_runtime_config",
                                                   return_value=types.SimpleNamespace(nice=0)))
            stack.enter_context(mock.patch.object(self.executor, "run_owned_process", side_effect=capture))
            with self.assertRaises(WorkerBoundary):
                self.executor._execute(
                    ["remote_sub_exec.py", RUN_ID, "glm",
                     str(self.physical / "tmp" / (RUN_ID + ".txt")), "~", MODEL],
                    {"entered_monotonic_ns": time.monotonic_ns(), "started": False})
        self.assertEqual(acquire.call_args.args[0], self.physical / "ext/active")
        self.assertEqual(reached["command"][2:5],
                         ["--prompt-file", "glm", str(self.physical / "tmp" / (RUN_ID + ".txt"))])
        self.assertEqual(reached["kwargs"]["receipt_path"],
                         self.physical / "ext/lanes" / (RUN_ID + ".process.jsonl"))

    def test_state_link_changed_after_admission_holds_without_worker(self):
        held = []
        case = self
        class Lease:
            def __enter__(inner):
                case.change_generation_link("active")
                return inner
            def __exit__(inner, *args):
                return False
            def hold_for_reconciliation(inner, reason):
                held.append(reason)
        with ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, self.executor_environment(), clear=True))
            stack.enter_context(mock.patch.object(self.executor.LaneLease, "acquire", return_value=Lease()))
            stack.enter_context(mock.patch.object(self.executor, "install_signal_cleanup"))
            stack.enter_context(mock.patch.object(self.executor, "load_runtime_config",
                                                   return_value=types.SimpleNamespace(nice=0)))
            runner = stack.enter_context(mock.patch.object(self.executor, "run_owned_process"))
            rc = self.executor._execute(
                ["remote_sub_exec.py", RUN_ID, "glm",
                 str(self.physical / "tmp" / (RUN_ID + ".txt")), "~", MODEL],
                {"entered_monotonic_ns": time.monotonic_ns(), "started": False})
        self.assertEqual(rc, 76)
        self.assertEqual(held, ["remote_lane_root_changed"])
        runner.assert_not_called()

    def writer_command(self, run_id):
        result = self.fx.run_helper(["lane-root-packet-command", self.layout_token, run_id])
        self.assertEqual(result.returncode, 0, result.stderr)
        args = shlex.split(result.stdout)
        self.assertEqual(args[:4], ["python3", "-I", "-S", "-c"])
        return [sys.executable, *args[1:]]

    def test_exclusive_packet_receiver_transports_bytes_once(self):
        run = "inert-fresh-packet"
        command = self.writer_command(run)
        result = subprocess.run(command, input=PACKET, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        path = self.physical / "tmp" / (run + ".txt")
        self.assertEqual(path.read_bytes(), PACKET)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        again = subprocess.run(command, input=b"replacement", capture_output=True, timeout=15)
        self.assertNotEqual(again.returncode, 0)
        self.assertEqual(path.read_bytes(), PACKET)

    def test_packet_leaf_collisions_do_not_write_through_or_overwrite(self):
        for kind in ("regular", "symlink", "hardlink"):
            run = "inert-existing-" + kind
            leaf = self.physical / "tmp" / (run + ".txt")
            target = self.physical / "tmp" / (run + "-target.txt")
            exclusive(target, b"preserve original\n")
            if kind == "regular":
                exclusive(leaf, b"preserve original\n")
            elif kind == "symlink":
                leaf.symlink_to(target.name)
            else:
                os.link(target, leaf)
            result = subprocess.run(self.writer_command(run), input=PACKET,
                                    capture_output=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(target.read_bytes(), b"preserve original\n")
            self.assertEqual(leaf.read_bytes(), b"preserve original\n")

    def test_existing_output_or_receipt_refuses_before_packet_write(self):
        for suffix, relative in ((".stdout", "ext"), (".rc", "ext"),
                                 (".process.jsonl", "ext/lanes")):
            run = "inert-old-output-" + suffix.lstrip(".").replace(".", "-")
            name = ("lanes_" + run if relative == "ext" else run) + suffix
            leaf = self.physical / relative / name
            exclusive(leaf, b"retained carrier\n")
            result = subprocess.run(self.writer_command(run), input=PACKET,
                                    capture_output=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(leaf.read_bytes(), b"retained carrier\n")
            self.assertFalse((self.physical / "tmp" / (run + ".txt")).exists())

    def test_output_reservation_keeps_existing_leaf_and_holds_fds(self):
        run = "inert-fresh-outputs"
        descriptors = self.delivery.open_remote_lane_outputs(self.layout, run)
        try:
            os.write(descriptors[0], b"inert stdout\n")
            os.write(descriptors[1], b"75\n")
        finally:
            for fd in descriptors:
                os.close(fd)
        with self.assertRaises(ValueError):
            self.delivery.open_remote_lane_outputs(self.layout, run)
        self.assertEqual((self.physical / "ext" / ("lanes_" + run + ".stdout")).read_bytes(),
                         b"inert stdout\n")
        self.assertEqual((self.physical / "ext" / ("lanes_" + run + ".rc")).read_bytes(), b"75\n")


    def test_generated_launch_entry_uses_exclusive_outputs_and_original_argv(self):
        run = "inert-generated-launch"
        entry_bin = Path(self._stack.name) / "launch-bin"
        entry_bin.mkdir(mode=0o700)
        shim = entry_bin / "python3"
        argv_file = self.fx.ctl / "executor-argv"
        exclusive(shim, ("#!/bin/sh\nprintf 'inert executor boundary\\n'\n"
                         "printf '%s\\n' \"$@\" > " + shlex.quote(str(argv_file)) +
                         "\nexit 75\n").encode(), 0o700)
        result = self.fx.run_helper(["lane-root-launch-command", self.layout_token, run])
        self.assertEqual(result.returncode, 0, result.stderr)
        command = shlex.split(result.stdout)
        self.assertEqual(command[:4], ["python3", "-I", "-S", "-c"])
        env = dict(os.environ, PATH=str(entry_bin) + os.pathsep + os.environ["PATH"],
                   LANE_DIRECTORY=str(self.physical), SUPPORT_DIGEST=self.fx.support_digest,
                   KEY=run, MODE="glm", PACKET=str(self.physical / "tmp" / (run + ".txt")),
                   REMOTE_CWD="~", MODEL=MODEL)
        launched = subprocess.run([sys.executable, *command[1:]], env=env,
                                  capture_output=True, text=True, timeout=15)
        self.assertEqual(launched.returncode, 0, launched.stderr)
        output = self.physical / "ext" / ("lanes_" + run + ".stdout")
        rc = self.physical / "ext" / ("lanes_" + run + ".rc")
        self.assertEqual(output.read_bytes(), b"inert executor boundary\n")
        self.assertEqual(rc.read_bytes(), b"75\n")
        self.assertEqual(argv_file.read_text().splitlines(),
                         [str(self.published / "remote_sub_exec.py"), run, "glm",
                          str(self.physical / "tmp" / (run + ".txt")), "~", MODEL])
        argv_file.unlink()
        again = subprocess.run([sys.executable, *command[1:]], env=env,
                               capture_output=True, text=True, timeout=15)
        self.assertNotEqual(again.returncode, 0)
        self.assertFalse(argv_file.exists())
        self.assertEqual(output.read_bytes(), b"inert executor boundary\n")
        self.assertEqual(rc.read_bytes(), b"75\n")

    def scope_shell(self, changes):
        # Execute the actual loader/fence; the suffix is the first possible
        # lease/remote/operator stage and must remain unreachable on refusal.
        values = dict(HERE=str(self.fx.ctl), REMOTE_SUB_PYTHON=sys.executable,
                      HOST_ARG=HOST, MODE="glm", RUN_ID_ARG=RUN_ID,
                      PLAIN_PACKET_RETAINED=str(self.fx.packet_pin),
                      POOL_ORCHESTRATOR_ID=ROOT, POOL_PARENT_RUN_ID=PARENT,
                      REMOTE_CWD="~", OPERATOR_CHILD_BUDGET="0",
                      NEW_MACRO_COMMIT="", CPU_SCOPE_QUOTA="", RC="0")
        values.update(changes)
        setup = "\n".join(k + "=" + shlex.quote(v) for k, v in values.items())
        script = ("set -u\n" + setup + "\n"
                  "log() { printf '%s\\n' \"$*\"; }\n"
                  "commission_run() { shift; \"$@\"; }\n" +
                  shell_function(self.shell, "load_host_registry") +
                  '\nload_host_registry || exit "$RC"\n'
                  "printf '%s\\n' EFFECT_BOUNDARY_REACHED\n")
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("FABRIC_OPERATOR_", "POOL_OPERATOR_"))}
        return subprocess.run(["bash", "-c", script], capture_output=True,
                              text=True, timeout=15, env=env)

    def test_actual_scope_fence_excludes_special_and_unsupported_shapes(self):
        self.assertEqual(self.scope_shell({}).returncode, 0)
        for changed in (
                {"FABRIC_OPERATOR_PRELEASE_CONTINUATION": RUN_ID},
                {"FABRIC_OPERATOR_POST_SUPPORT_CONTINUATION": RUN_ID},
                {"FABRIC_OPERATOR_CHILD_ID": "child"},
                {"MODE": "glm-codex"}, {"MODE": "grok"},
                {"RUN_ID_ARG": ""}, {"PLAIN_PACKET_RETAINED": ""},
                {"POOL_PARENT_RUN_ID": ""}, {"REMOTE_CWD": "/tmp"},
                {"OPERATOR_CHILD_BUDGET": "1"}, {"NEW_MACRO_COMMIT": "a" * 40},
                {"CPU_SCOPE_QUOTA": "100"}):
            with self.subTest(changed=changed):
                result = self.scope_shell(changed)
                self.assertEqual(result.returncode, 78, result.stdout + result.stderr)
                self.assertIn("before_lease=1 before_remote=1", result.stdout)
                self.assertNotIn("EFFECT_BOUNDARY_REACHED", result.stdout)
        self.write_registry({k: v for k, v in self.entry.items() if k != "physical_lane_root"})
        result = self.scope_shell({"FABRIC_OPERATOR_CHILD_ID": "legacy-child"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_local_shortcut_refuses_configured_root_before_worker(self):
        replace_private(self.fx.ctl / "hosts.json", json.dumps({"m2": self.entry}).encode())
        exclusive(self.fx.ctl / "sub.sh", b"#!/bin/bash\nprintf 'INERT_LOCAL_BOUNDARY\\n'\n", 0o700)
        branch = self.shell.split('if [ "$HOST_ARG" = m2 ]; then\n', 1)[1].split(
            "\n# The same canonical registry constraints", 1)[0]
        setup = dict(HOST_ARG="m2", HERE=str(self.fx.ctl), REMOTE_SUB_PYTHON=sys.executable,
                     COMMISSION_ACTIVE="0", OPERATOR_CHILD_BUDGET="0", DRY_RUN="0",
                     PACKET=str(self.fx.packet_pin), PACKET_BASE="inert.packet",
                     REMOTE_CWD="~", MODEL=MODEL, MODE="glm")
        prefix = "set -u\n" + "\n".join(k + "=" + shlex.quote(v) for k, v in setup.items())
        script = prefix + '\nlog() { printf "%s\\n" "$*"; }\nif [ "$HOST_ARG" = m2 ]; then\n' + branch
        env = {k: v for k, v in os.environ.items() if not k.startswith("FABRIC_OPERATOR_")}
        result = subprocess.run(["bash", "-c", script], capture_output=True,
                                text=True, timeout=15, env=env)
        self.assertEqual(result.returncode, 78, result.stdout + result.stderr)
        self.assertNotIn("INERT_LOCAL_BOUNDARY", result.stdout)
        replace_private(self.fx.ctl / "hosts.json", json.dumps({"m2": {
            k: v for k, v in self.entry.items() if k != "physical_lane_root"}}).encode())
        result = subprocess.run(["bash", "-c", script], capture_output=True,
                                text=True, timeout=15, env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("INERT_LOCAL_BOUNDARY", result.stdout)

    def test_actual_launch_loop_does_not_repeat_busy_bound_admission(self):
        retry = self.shell.split("RETRYABLE_ADMISSION_MODE=0\n", 1)[1].split(
            "\ncommission_refresh_runtime prelease", 1)[0]
        loop = self.shell.split('ADMISSION_FILE="$HERE/lanes/', 1)[1].split(
            "\n", 1)[1].split("\nrequire_bound_lane_layout_after_launch before_collection", 1)[0]
        vals = {
            "HERE": str(self.fx.ctl), "MODE": "glm", "REMOTE_PHYSICAL_ROOT": str(self.physical),
            "ADMISSION_WAIT_SECS": "20", "ADMISSION_RETRY_SECS": "2", "DRY_RUN": "0",
            "ADMISSION_FILE": str(self.fx.ctl / "admission"), "COMMISSION_ACTIVE": "0",
            "RC_OBSERVED": "0", "NATIVE_MODE": "0", "ID": RUN_ID, "HOST_ARG": HOST,
            "REMOTE_LANE_ROOT_EXPR": str(self.physical), "REMOTE_LANE_TRANSFER": str(self.physical),
            "REMOTE_STDOUT": "lanes_" + RUN_ID + ".stdout", "REMOTE_RC": "lanes_" + RUN_ID + ".rc",
            "REMOTE_CWD": "~", "MODEL": MODEL, "LANE_ROOT_LAYOUT_TOKEN": self.layout_token,
            "LANE_ROOT_PACKET_SHA": sha(PACKET), "SUPPORT_DIGEST": self.fx.support_digest,
            "SSH_CMD": "inert-ssh", "SSH_ALIAS": ALIAS, "ACCOUNT_ARG": ALIAS,
            "NATIVE_TIMING_PREFIX": "", "NATIVE_TIMING_AFTER_ENV": "", "NATIVE_TIMING_ENV": "",
            "ROUTING_ENV": "", "OPERATOR_ENV": "", "RPATH": ":", "HOST_ENV": ":",
            "REMOTE_INNER": "inert-worker-boundary", "LEASE_ID": "",
            "NATIVE_LEASE_ISSUED": "", "NATIVE_LEASE_DEADLINE": "", "MAX_ACTIVE": "2",
            "MIN_FREE_MEM_GB": "0", "MAX_CPU_TCTL_C": "0", "MIN_FREE_DISK_GB": "0",
            "NEW_MACRO_COMMIT": "", "CPU_SCOPE_QUOTA": "", "LANE_HOST_LOAD_RATIO": "1",
            "POLL_FILE": str(self.fx.ctl / "poll"), "MAX_SECS": "10", "POLL_SECS": "1",
            "REMOTE_OUTPUT_SETUP": ":", "REMOTE_LAUNCH_EXEC": "true",
            "REMOTE_OUTPUT_REDIRECT": ">/dev/null 2>&1"}
        setup = "\n".join(k + "=" + shlex.quote(v) for k, v in vals.items())
        script = ("set -u\n" + setup + "\ndeclare -a SCRATCH_PATHS=()\n"
                  "log() { printf '%s\\n' \"$*\"; }\n"
                  "commission_refresh_runtime() { CHILD_TIMEOUT=9; return 0; }\n"
                  "require_bound_lane_layout_after_launch() { return 0; }\n"
                  "commission_run() {\n case \"$1\" in\n"
                  " launch) printf '%s\\n' INERT_LAUNCH; return 0;;\n"
                  " poll) printf '75\\n'; return 0;;\n"
                  " *) printf 'UNEXPECTED_STAGE %s\\n' \"$1\" >&2; return 99;;\n"
                  " esac\n}\nRETRYABLE_ADMISSION_MODE=0\n" + retry + "\n" + loop +
                  '\nprintf "FINAL_RC=%s ATTEMPTS=%s\\n" "$RC" "$launch_attempt"\n')
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count("INERT_LAUNCH"), 1)
        self.assertIn("FINAL_RC=75 ATTEMPTS=1", result.stdout)
        self.assertNotIn("ADMISSION_RETRY", result.stdout)

    def supervised_check(self, *, expired=False):
        for name in ("lane_runtime.py", "commission_deadline.py"):
            source = CAND / name
            if not source.exists():
                source = SRC / name
            shutil.copyfile(source, self.fx.ctl / name)
        ssh = self.fx.ctl / "hung-ssh"
        marker = self.fx.ctl / "ssh-started"
        exclusive(ssh, (f"#!{sys.executable}\nimport time\nfrom pathlib import Path\n"
                        f"Path({str(marker)!r}).write_text('inert started')\n"
                        "time.sleep(30)\n").encode(), 0o700)
        receipt = self.fx.ctl / "deadline-process.jsonl"
        setup = {
            "REMOTE_PHYSICAL_ROOT": str(self.physical), "SSH_CMD": str(ssh),
            "SSH_ALIAS": ALIAS, "LANE_ROOT_LAYOUT_TOKEN": self.layout_token,
            "PLAIN_TRANSPORT_CHAIN_SOURCE": self.delivery.remote_directory_chain_source(),
            "HERE": str(self.fx.ctl), "REMOTE_SUB_PYTHON": sys.executable,
            "COMMISSION_ACTIVE": "1", "PRESERVE_LEASE": "0", "RC": "0"}
        script = "set -u\n" + "\n".join(k + "=" + shlex.quote(v) for k, v in setup.items()) + "\n"
        script += "log() { printf '%s\\n' \"$*\" >&2; }\n"
        for name in ("commission_command", "commission_run", "check_bound_lane_layout",
                     "require_bound_lane_layout_after_launch"):
            script += shell_function(self.shell, name)
        script += """trap 'printf "PRESERVE_LEASE=%s\\n" "$PRESERVE_LEASE"' EXIT
require_bound_lane_layout_after_launch poll
printf 'UNEXPECTED_WORKER_LAUNCH\n'
"""
        env = dict(os.environ)
        env["POOL_COMMISSION_DEADLINE_NS"] = str(
            time.monotonic_ns() + (-1 if expired else 1_000_000_000))
        env["REMOTE_SUB_DEADLINE_PROCESS_RECEIPT"] = str(receipt)
        result = subprocess.run(["bash", "-c", script], capture_output=True,
                                text=True, timeout=10, env=env)
        return result, receipt, marker

    def test_hung_root_check_uses_existing_deadline_and_preserves_uncertainty(self):
        result, receipt, marker = self.supervised_check()
        self.assertEqual(result.returncode, 76, result.stdout + result.stderr)
        self.assertTrue(marker.exists())
        self.assertIn("PRESERVE_LEASE=1", result.stdout)
        self.assertNotIn("UNEXPECTED_WORKER_LAUNCH", result.stdout)
        row = json.loads(receipt.read_text().splitlines()[-1])
        self.assertEqual(row["label"], "commission-lane-root-check")
        self.assertTrue(row["timed_out"])
        self.assertEqual(row["returncode"], 75)
        self.assertEqual(row["cleanup"]["residual_count"], 0)

    def test_expired_root_check_never_starts_transport_or_worker(self):
        result, receipt, marker = self.supervised_check(expired=True)
        self.assertEqual(result.returncode, 76, result.stdout + result.stderr)
        self.assertFalse(marker.exists())
        self.assertFalse(receipt.exists())
        self.assertIn("PRESERVE_LEASE=1", result.stdout)
        self.assertNotIn("UNEXPECTED_WORKER_LAUNCH", result.stdout)


    def actual_poll(self):
        line = next(line for line in self.shell.splitlines()
                    if '"if [ -f \\"$REMOTE_LANE_ROOT_EXPR/ext/$REMOTE_RC\\"' in line)
        expression = line.strip().split(' > "$POLL_FILE"', 1)[0]
        values = {"REMOTE_PHYSICAL_ROOT": str(self.physical),
                  "REMOTE_LANE_ROOT_EXPR": str(self.physical),
                  "REMOTE_RC": "lanes_" + RUN_ID + ".rc"}
        script = "\n".join(k + "=" + shlex.quote(v) for k, v in values.items())
        script += "\ncommand=" + expression + '\nbash -c "$command"\n'
        return subprocess.run(["bash", "-c", script], capture_output=True,
                              text=True, timeout=10)

    def test_running_reserved_rc_is_pending_then_original_terminal_code(self):
        self.qualified()
        rc_path = self.physical / "ext" / ("lanes_" + RUN_ID + ".rc")
        stdout_path = self.physical / "ext" / ("lanes_" + RUN_ID + ".stdout")
        process_path = self.physical / "ext/lanes" / (RUN_ID + ".process.jsonl")
        for path in (rc_path, stdout_path, process_path):
            path.unlink()
        ready = self.fx.ctl / "inert-running"
        release = self.fx.ctl / "inert-release"
        entry_bin = Path(self._stack.name) / "launch-bin"
        entry_bin.mkdir(mode=0o700)
        shim = entry_bin / "python3"
        stub = (f"#!{sys.executable}\nimport time\nfrom pathlib import Path\n"
                f"Path({str(ready)!r}).write_text('running')\n"
                "until=time.monotonic()+10\n"
                f"while not Path({str(release)!r}).exists() and time.monotonic()<until:\n"
                "    time.sleep(0.02)\n"
                "raise SystemExit(75)\n")
        exclusive(shim, stub.encode(), 0o700)
        result = self.fx.run_helper(["lane-root-launch-command", self.layout_token, RUN_ID])
        self.assertEqual(result.returncode, 0, result.stderr)
        command = shlex.split(result.stdout)
        env = dict(os.environ, PATH=str(entry_bin) + os.pathsep + os.environ["PATH"],
                   LANE_DIRECTORY=str(self.physical), SUPPORT_DIGEST=self.fx.support_digest,
                   KEY=RUN_ID, MODE="glm", PACKET=str(self.physical / "tmp" / (RUN_ID + ".txt")),
                   REMOTE_CWD="~", MODEL=MODEL)
        process = subprocess.Popen([sys.executable, *command[1:]], env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            until = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < until:
                if process.poll() is not None:
                    break
                time.sleep(0.02)
            self.assertTrue(ready.exists())
            self.assertIsNone(process.poll())
            self.assertEqual(rc_path.read_bytes(), b"")
            poll = self.actual_poll()
            self.assertEqual(poll.returncode, 0, poll.stderr)
            self.assertEqual(poll.stdout, "__REMOTE_SUB_PENDING__\n")
            receipt = self.collect()
            self.assertEqual(receipt["state"], "PENDING")
            self.assertFalse(receipt["delivery_verified"])
            self.assertFalse(receipt["worker_terminal_proof"])
            self.assertEqual(receipt["acceptance"], "NOT_RECORDED")
            self.assertIsNone(process.poll())
        finally:
            release.write_text("finish inert executor")
            stdout, stderr = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, stdout + stderr)
        self.assertEqual(rc_path.read_bytes(), b"75\n")
        self.assertEqual(self.actual_poll().stdout, "75\n")
        request = json.loads((Path(self.fx.destination) / "read-request.json").read_bytes())
        observed = self.delivery.transport(ALIAS, request)
        self.assertEqual(json.loads(observed)["state"], "NONZERO")
        with self.assertRaisesRegex(ValueError, "terminal_delivery_unqualified"):
            self.collector.validate_response(observed, request, "glm")

    def test_nonempty_malformed_rc_remains_refused(self):
        self.qualified()
        replace_private(self.physical / "ext" / ("lanes_" + RUN_ID + ".rc"), b"unknown\n")
        with self.assertRaisesRegex(ValueError, "original_rc_invalid"):
            self.collect()


if __name__ == "__main__":
    unittest.main(verbosity=2)
