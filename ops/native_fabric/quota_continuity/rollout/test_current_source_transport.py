"""Focused inert test for the CURRENT source composition's transport half.

The incumbent strict-SSH bounded transport in artifact_delivery must dispatch
the current-source schema to the exact fixed generated reader and be incapable
of carrying any caller-shaped command.  The "ssh" binary is mocked here by a
local interpreter running that same generated reader; there is no network, no
real host and no live state.
"""
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.abspath(os.path.join(HERE, ".."))
CANDIDATE = os.path.join(STAGE, "candidate")
SOURCE = os.path.join(STAGE, "source")
# Candidate overlays take precedence over installed preimages.
for _path in (SOURCE, CANDIDATE):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import test_current_source_observation as base
from test_current_source_observation import (Host, TestChain, inert_request_loader)
# One shared module instance: the owner boundary, the invocation type and the
# composition entry points must all come from the same loaded module.
cso = base.cso
import artifact_delivery


class CurrentSourceTransportTests(Host):
    def test_transport_dispatches_exact_generated_reader(self):
        request = self.request(repo=self.worktree)
        owner = self.owner(repo=self.worktree)
        invocation = self.mint(request, owner)
        expected = cso.observe_remote(request)
        real_popen = artifact_delivery.subprocess.Popen
        recorded = {}

        def mocked_ssh(argv, **kwargs):
            recorded["argv"] = argv
            recorded["kwargs"] = kwargs
            self.assertEqual(argv[0], "ssh")
            self.assertEqual(argv[1:7],
                             ["-o", "BatchMode=yes",
                              "-o", "StrictHostKeyChecking=yes",
                              "-o", "ConnectTimeout=8"])
            self.assertEqual(argv[7], owner.alias)
            command = argv[8]
            self.assertTrue(command.startswith("python3 -I -S -c "), command[:80])
            tokens = shlex.split(command)
            self.assertEqual(tokens[:4], ["python3", "-I", "-S", "-c"])
            # The remote program is exactly the fixed generated reader, never
            # anything derived from caller bytes.
            self.assertEqual(tokens[4], cso.generated_reader_source())
            self.assertNotIn(cso.canonical(request).decode("ascii"), command)
            self.assertNotIn("&&", command)
            self.assertIsNone(kwargs.get("shell"))
            return real_popen([sys.executable, "-I", "-S", "-c", tokens[4]],
                              **kwargs)

        artifact_delivery.subprocess.Popen = mocked_ssh
        try:
            raw = artifact_delivery.transport(owner.alias, request)
            self.assertEqual(cso.strict_json(raw), expected)
            # The full composition through the incumbent transport function.
            response = cso.observe_current_source(
                request, invocation,
                lambda req, alias=owner.alias: artifact_delivery.transport(alias, req))
        finally:
            artifact_delivery.subprocess.Popen = real_popen
        self.assertEqual(response["status"], "OBSERVED", response)
        cso.validate_response(response)
        self.assertEqual(response["receipt"]["receiver"], "receiver-1")

    def test_transport_carries_no_caller_shaped_command(self):
        # Hostile receiver/path bytes are refused by admission and validation
        # before any process is spawned: the transport cannot be asked to run
        # anything else.
        hostile = self.request(receiver="receiver-1; cat /etc/shadow")
        owner = self.owner()
        real_popen = artifact_delivery.subprocess.Popen

        def refusing(*args, **kwargs):
            raise AssertionError("a process was spawned for a refused request")

        spawned = []

        def refusing(*args, **kwargs):
            spawned.append(args)
            raise AssertionError("a process was spawned for a refused request")

        artifact_delivery.subprocess.Popen = refusing
        try:
            response = cso.observe_current_source(
                hostile, None,
                lambda req: artifact_delivery.transport(owner.alias, req))
        finally:
            artifact_delivery.subprocess.Popen = real_popen
        # Closed-world validation refuses before admission and before any
        # read or process; caller bytes never reach the command line.
        self.assertRefused(response, "identity_invalid", state="NOT_SEEKED")
        self.assertEqual(spawned, [])

    def test_end_to_end_receiver_bound_receipt_via_incumbent_transport(self):
        request = self.request(repo=self.worktree)
        real_popen = artifact_delivery.subprocess.Popen

        def mocked_ssh(argv, **kwargs):
            tokens = shlex.split(argv[8])
            return real_popen([sys.executable, "-I", "-S", "-c", tokens[4]],
                              **kwargs)

        with tempfile.TemporaryDirectory(prefix="cso-req-") as req_dir:
            request_path = os.path.join(req_dir, "request.json")
            with open(request_path, "wb") as handle:
                handle.write(cso.canonical(request))
            registry = {"ubuntu2": {"allowed_modes": ["current-source"],
                                    "ssh_alias": "fixture-host-alias"}}
            factory = base.make_owner_factory(registry)
            artifact_delivery.subprocess.Popen = mocked_ssh
            try:
                with tempfile.TemporaryDirectory(prefix="cso-dest-") as dest:
                    with mock.patch.dict(os.environ, CODEX_THREAD_ID=request["observer"]):
                        summary = cso.native_current_source_receipt(
                            request_path, dest, factory, reserve=TestChain,
                            load_request=inert_request_loader)
                    self.assertEqual(summary["state"], "PUBLISHED", summary)
                    with open(summary["destination"], "rb") as handle:
                        stored = json.loads(handle.read().decode())
            finally:
                artifact_delivery.subprocess.Popen = real_popen
            cso.validate_response(stored)
            receipt = stored["receipt"]
            self.assertEqual(receipt["receiver"], "receiver-1")
            self.assertEqual(receipt["root"], "root-current-1")
            self.assertEqual(receipt["commit"], request["commit"])
            self.assertEqual(receipt["no_claims"], list(cso.NO_CLAIMS))
            self.assertEqual(receipt["request_sha256"],
                             cso.validate_request(request))
            self.assertEqual(os.path.basename(summary["destination"]),
                             "current-source-%s.json"
                             % receipt["response_sha256"][:16])

    def test_registry_without_installed_mode_stays_not_live(self):
        request = self.request(repo=self.worktree)
        registry = {"ubuntu2": {"allowed_modes": ["glm"],
                                "ssh_alias": "fixture-host-alias"}}
        factory = base.make_owner_factory(registry)
        digest = cso.validate_request(request)
        owner = factory(digest)
        self.assertFalse(owner.admit_invocation(
            cso.NativeInvocationView.of(request, digest), os.getuid()))
        self.assertIsNone(owner.transport_alias(
            cso.NativeInvocationView.of(request, digest)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
