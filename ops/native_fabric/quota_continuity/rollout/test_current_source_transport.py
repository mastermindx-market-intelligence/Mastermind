"""Focused inert test for the CURRENT source composition's transport half.

The incumbent strict-SSH bounded transport in artifact_delivery must dispatch
the current-source schema to the exact fixed generated reader and be incapable
of carrying any caller-shaped command.  The "ssh" binary is mocked here by a
local interpreter running that same generated reader; there is no network, no
real host and no live state.
"""
import base64
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
from test_current_source_observation import (Host, TestChain, inert_request_loader,
                                             build_repo, run_git)
# One shared module instance: the owner boundary, the invocation type and the
# composition entry points must all come from the same loaded module.
cso = base.cso
try:
    import artifact_delivery
except ImportError as exc:
    artifact_delivery = None
    _ARTIFACT_DELIVERY_IMPORT_ERROR = exc


class CurrentSourceTransportTests(Host):
    def setUp(self):
        if artifact_delivery is None:
            self.skipTest("incumbent artifact_delivery dependencies unavailable: %s"
                          % _ARTIFACT_DELIVERY_IMPORT_ERROR)

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
            registry = {"ubuntu2": {"roles": ["lanes"], "allowed_modes": ["glm"],
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

    def test_registry_without_lane_role_refuses(self):
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


class CustodyTransportTests(Host):
    """The additive worktree_pointer_graph custody variant over the real
    incumbent strict-SSH transport (ssh mocked to the local interpreter
    running the same generated reader) and the native CLI publication path.
    The shipped remote program stays the exact fixed generated reader; the
    request travels on stdin only."""

    def setUp(self):
        if artifact_delivery is None:
            self.skipTest("incumbent artifact_delivery dependencies unavailable: %s"
                          % _ARTIFACT_DELIVERY_IMPORT_ERROR)

    def mocked_ssh(self, expected_alias, request):
        real_popen = artifact_delivery.subprocess.Popen

        def spawn(argv, **kwargs):
            self.assertEqual(argv[0], "ssh")
            self.assertEqual(argv[1:7],
                             ["-o", "BatchMode=yes",
                              "-o", "StrictHostKeyChecking=yes",
                              "-o", "ConnectTimeout=8"])
            self.assertEqual(argv[7], expected_alias)
            command = argv[8]
            prefix = "python3 -I -S -c "
            self.assertTrue(command.startswith(prefix), command[:80])
            tokens = shlex.split(command)
            self.assertEqual(tokens[:4], ["python3", "-I", "-S", "-c"])
            # The remote program is exactly the fixed generated reader, the
            # same bytes a triple-mode request receives: the custody variant
            # rides the reviewed seam, never a caller-shaped program.
            self.assertEqual(tokens[4], cso.generated_reader_source())
            self.assertNotIn(cso.canonical(request).decode("ascii"), command)
            self.assertNotIn("&&", command)
            self.assertIsNone(kwargs.get("shell"))
            return real_popen([sys.executable, "-I", "-S", "-c", tokens[4]],
                              **kwargs)

        return spawn

    def test_transport_executes_generated_reader_for_linked_custody(self):
        request = self.custody_request(repo=self.worktree)
        invocation = self.mint(request, self.custody_owner(request))
        real_popen = artifact_delivery.subprocess.Popen
        artifact_delivery.subprocess.Popen = self.mocked_ssh("fixture-host-alias",
                                                             request)
        try:
            raw = artifact_delivery.transport("fixture-host-alias", request)
            body = cso.strict_json(raw)
            self.assertEqual(body["status"], "OBSERVED", body)
            response = cso.observe_current_source(
                request, invocation,
                lambda req: artifact_delivery.transport("fixture-host-alias", req))
        finally:
            artifact_delivery.subprocess.Popen = real_popen
        self.assertEqual(response["status"], "OBSERVED", response)
        cso.validate_response(response)
        self.assertEqual(response["git_dir"], self.wt_git_dir)
        self.assertEqual(response["common_dir"], self.wt_common_dir)
        proof = response["resolution"]
        self.assertEqual(base64.b64decode(proof["git_link"]["bytes_b64"]).decode(),
                         self.wt_gitfile)
        self.assertEqual(
            base64.b64decode(proof["gitdir_backlink"]["bytes_b64"]).decode().strip(),
            self.worktree + "/.git")
        self.assertEqual(
            base64.b64decode(proof["commondir"]["bytes_b64"]).decode().strip(),
            "../..")
        self.assertEqual(response["receipt"]["request_sha256"],
                         cso.validate_request(request))

    def test_native_cli_publishes_linked_custody_and_refuses_escape(self):
        request = self.custody_request(repo=self.worktree)
        registry = {"ubuntu2": {"roles": ["lanes"], "allowed_modes": ["glm"],
                                "ssh_alias": "fixture-host-alias"}}
        factory = base.make_owner_factory(registry)
        # Discriminating refusal fixture first: a real linked worktree whose
        # gitfile resolves outside the declared boundary.  Building it needs
        # plain git, so it happens before the ssh mock is installed.
        outside = build_repo(self.base, "out-repo")
        bound = os.path.join(self.base, "bound")
        os.makedirs(bound, exist_ok=True)
        run_git(outside, "worktree", "add", "-q", os.path.join(bound, "wt"),
                "-b", "wt-out")
        escape = self.custody_request(repo=os.path.join(bound, "wt"),
                                      boundary=bound)
        real_popen = artifact_delivery.subprocess.Popen
        artifact_delivery.subprocess.Popen = self.mocked_ssh("fixture-host-alias",
                                                             request)
        try:
            with tempfile.TemporaryDirectory(prefix="custody-req-") as req_dir:
                request_path = os.path.join(req_dir, "request.json")
                with open(request_path, "wb") as handle:
                    handle.write(cso.canonical(request))
                with open(os.path.join(req_dir, "escape.json"), "wb") as handle:
                    handle.write(cso.canonical(escape))
                with tempfile.TemporaryDirectory(prefix="custody-dest-") as dest:
                    with mock.patch.dict(os.environ,
                                         CODEX_THREAD_ID=request["observer"]):
                        summary = cso.native_current_source_receipt(
                            request_path, dest, factory, reserve=TestChain,
                            load_request=inert_request_loader)
                    self.assertEqual(summary["state"], "PUBLISHED", summary)
                    with open(summary["destination"], "rb") as handle:
                        stored = json.loads(handle.read().decode())
                cso.validate_response(stored)
                self.assertEqual(stored["git_dir"], self.wt_git_dir)
                self.assertIn("resolution", stored)
                self.assertEqual(stored["receipt"]["receiver"], "receiver-1")

                # Admission succeeds, the actual generated reader refuses, and
                # nothing is published into the reserved destination.
                with tempfile.TemporaryDirectory(prefix="custody-dest-") as dest:
                    with mock.patch.dict(os.environ,
                                         CODEX_THREAD_ID=escape["observer"]):
                        refused = cso.native_current_source_receipt(
                            os.path.join(req_dir, "escape.json"), dest, factory,
                            reserve=TestChain,
                            load_request=inert_request_loader)
                    self.assertEqual(refused["state"], "REFUSED", refused)
                    self.assertEqual(refused["reason"], "custody_resolution_invalid",
                                     refused)
                    self.assertEqual(refused["admission_state"], "ADMITTED", refused)
                    # No partial bytes: the refused observation published
                    # nothing into the reserved destination.
                    self.assertEqual(os.listdir(dest), [])
        finally:
            artifact_delivery.subprocess.Popen = real_popen


class UnderscoreTransportTests(Host):
    """The exact eight leading-underscore source paths through the real
    incumbent strict-SSH bounded transport: "ssh" is mocked by the local
    isolated interpreter running the same fixed generated reader.  There is no
    network, no real host, and no fabricated positive callback -- the only
    OBSERVED bodies come from the generated reader's own custody checks and
    object reads over the stdin-only request."""

    def setUp(self):
        if artifact_delivery is None:
            self.skipTest("incumbent artifact_delivery dependencies unavailable: %s"
                          % _ARTIFACT_DELIVERY_IMPORT_ERROR)

    def mocked_ssh(self, expected_alias, request):
        real_popen = artifact_delivery.subprocess.Popen

        def spawn(argv, **kwargs):
            self.assertEqual(argv[0], "ssh")
            self.assertEqual(argv[1:7],
                             ["-o", "BatchMode=yes",
                              "-o", "StrictHostKeyChecking=yes",
                              "-o", "ConnectTimeout=8"])
            self.assertEqual(argv[7], expected_alias)
            command = argv[8]
            prefix = "python3 -I -S -c "
            self.assertTrue(command.startswith(prefix), command[:80])
            tokens = shlex.split(command)
            self.assertEqual(tokens[:4], ["python3", "-I", "-S", "-c"])
            # The remote program is exactly the fixed generated reader -- the
            # same bytes for these underscore paths as for any other request;
            # the eight paths ride stdin only and never shape the command.
            self.assertEqual(tokens[4], cso.generated_reader_source())
            self.assertNotIn(cso.canonical(request).decode("ascii"), command)
            self.assertNotIn("__tests__", command)
            self.assertNotIn("&&", command)
            self.assertIsNone(kwargs.get("shell"))
            return real_popen([sys.executable, "-I", "-S", "-c", tokens[4]],
                              **kwargs)

        return spawn

    def test_incumbent_transport_executes_reader_for_all_eight(self):
        request = self.eight_request()
        invocation = self.mint(request, self.owner_bound(request))
        fixture = self.eight_fixture()
        root_tree = run_git(fixture["repo"], "rev-parse",
                            fixture["commit"] + "^{tree}")
        real_popen = artifact_delivery.subprocess.Popen
        artifact_delivery.subprocess.Popen = self.mocked_ssh(
            "fixture-host-alias", request)
        try:
            # The incumbent transport genuinely executes the fixed generated
            # reader for this exact eight-path request.
            raw = artifact_delivery.transport("fixture-host-alias", request)
            self.assertEqual(cso.strict_json(raw), cso.observe_remote(request))
            # The full composition rides the same incumbent seam.
            response = cso.observe_current_source(
                request, invocation,
                lambda req: artifact_delivery.transport("fixture-host-alias",
                                                        req))
        finally:
            artifact_delivery.subprocess.Popen = real_popen
        self.assertEightPathsBound(request, response, root_tree)
        cso.validate_response(response)
        self.assertEqual(response["receipt"]["request_sha256"],
                         cso.validate_request(request))
        self.assertEqual(response["receipt"]["receiver"], "receiver-1")

    def test_incumbent_transport_linked_custody_all_eight(self):
        # The resolution variant over a real linked worktree of the eight-path
        # store, through the same incumbent transport and generated reader.
        request = self.eight_request(linked=True)
        invocation = self.mint(request, self.owner_bound(request))
        fixture = self.eight_fixture()
        root_tree = run_git(fixture["repo"], "rev-parse",
                            fixture["commit"] + "^{tree}")
        real_popen = artifact_delivery.subprocess.Popen
        artifact_delivery.subprocess.Popen = self.mocked_ssh(
            "fixture-host-alias", request)
        try:
            response = cso.observe_current_source(
                request, invocation,
                lambda req: artifact_delivery.transport("fixture-host-alias",
                                                        req))
        finally:
            artifact_delivery.subprocess.Popen = real_popen
        self.assertEightPathsBound(request, response, root_tree)
        cso.validate_response(response)
        self.assertIn("resolution", response)
        with open(os.path.join(fixture["linked"], ".git")) as handle:
            git_dir = handle.read().split("gitdir: ", 1)[1].strip()
        self.assertEqual(response["git_dir"], git_dir)
        self.assertEqual(response["common_dir"],
                         os.path.join(fixture["repo"], ".git"))

    def test_native_receipt_publishes_all_eight_via_incumbent_transport(self):
        request = self.eight_request()
        fixture = self.eight_fixture()
        root_tree = run_git(fixture["repo"], "rev-parse",
                            fixture["commit"] + "^{tree}")
        registry = {"ubuntu2": {"roles": ["lanes"], "allowed_modes": ["glm"],
                                "ssh_alias": "fixture-host-alias"}}
        factory = base.make_owner_factory(registry)
        spawns = []
        inner = self.mocked_ssh("fixture-host-alias", request)
        real_popen = artifact_delivery.subprocess.Popen

        def wrapped(argv, **kwargs):
            spawns.append(argv)
            return inner(argv, **kwargs)

        with tempfile.TemporaryDirectory(prefix="cso-req-") as req_dir:
            request_path = os.path.join(req_dir, "request.json")
            with open(request_path, "wb") as handle:
                handle.write(cso.canonical(request))
            artifact_delivery.subprocess.Popen = wrapped
            try:
                with tempfile.TemporaryDirectory(prefix="cso-dest-") as dest:
                    with mock.patch.dict(os.environ,
                                         CODEX_THREAD_ID=request["observer"]):
                        summary = cso.native_current_source_receipt(
                            request_path, dest, factory, reserve=TestChain,
                            load_request=inert_request_loader)
                    self.assertEqual(summary["state"], "PUBLISHED", summary)
                    self.assertEqual(os.listdir(dest),
                                     [os.path.basename(summary["destination"])])
                    with open(summary["destination"], "rb") as handle:
                        stored = json.loads(handle.read().decode())
            finally:
                artifact_delivery.subprocess.Popen = real_popen
        # Exactly one real transport spawn carried the whole request; the
        # published receipt binds the original request and all eight blobs.
        self.assertEqual(len(spawns), 1)
        cso.validate_response(stored)
        self.assertEightPathsBound(request, stored, root_tree)
        receipt = stored["receipt"]
        self.assertEqual(receipt["request_sha256"], cso.validate_request(request))
        self.assertEqual(receipt["receiver"], request["receiver"])
        self.assertEqual(receipt["root"], request["root"])
        self.assertEqual(receipt["commit"], request["commit"])
        self.assertEqual(receipt["no_claims"], list(cso.NO_CLAIMS))
        self.assertEqual(os.path.basename(summary["destination"]),
                         "current-source-%s.json"
                         % receipt["response_sha256"][:16])

    def test_refused_underscore_path_spawns_nothing_incumbent(self):
        # A trailing-slash path is refused in closed-world validation before
        # admission, so the incumbent seam spawns no process at all and no
        # destination can appear.
        request = self.eight_request()
        request["sources"] = [{"path": "terminal/lib/__tests__/"}]
        real_popen = artifact_delivery.subprocess.Popen

        def refusing(*args, **kwargs):
            self.fail("a refused request spawned a process")

        artifact_delivery.subprocess.Popen = refusing
        try:
            response = cso.observe_current_source(
                request, None,
                lambda req: artifact_delivery.transport("fixture-host-alias",
                                                        req))
        finally:
            artifact_delivery.subprocess.Popen = real_popen
        self.assertRefused(response, "path_invalid", state="NOT_SEEKED")
        self.assertEqual(response["files"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
