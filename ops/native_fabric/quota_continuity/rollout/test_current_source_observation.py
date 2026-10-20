"""Discriminating inert tests for the bounded CURRENT source observation module.

Everything runs on synthetic fixtures inside owned temp directories.  No real
target host, no network, no live state.  Fixture Git writes are permitted only
inside the owned tempfile repositories the tests create here.  Native
invocations are compiled only at the inert fixture-owner boundary defined in
this file; untrusted JSON never constructs one.
"""
import base64
import copy
import hashlib
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
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

MODULE_PATH = os.path.join(CANDIDATE, "current_source_observation.py")
_spec = importlib.util.spec_from_file_location("current_source_observation", MODULE_PATH)
cso = importlib.util.module_from_spec(_spec)
sys.modules["current_source_observation"] = cso
_spec.loader.exec_module(cso)

GIT = "/usr/bin/git" if os.path.exists("/usr/bin/git") else shutil.which("git")

FILES = {
    "src/alpha.py": b'print("alpha current")\n',
    "docs/beta.txt": b"beta current bytes\n",
}


def run_git(repo, *args):
    result = subprocess.run([GIT] + list(args), cwd=repo, check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout.decode().strip()


def build_repo(root: str, name: str) -> str:
    repo = os.path.join(root, name)
    os.makedirs(repo)
    run_git(repo, "init", "-q", "-b", "main", ".")
    for path, data in FILES.items():
        os.makedirs(os.path.dirname(os.path.join(repo, path)), exist_ok=True)
        with open(os.path.join(repo, path), "wb") as handle:
            handle.write(data)
    run_git(repo, "add", ".")
    run_git(repo, "-c", "user.email=t@example.invalid", "-c", "user.name=t",
            "commit", "-q", "-m", "fixture-current")
    return repo


def tree_of(repo: str) -> dict:
    listing = run_git(repo, "ls-tree", "-r", "HEAD")
    entries = {}
    for line in listing.splitlines():
        meta, path = line.split("\t", 1)
        _mode, _kind, oid = meta.split()
        with open(os.path.join(repo, path), "rb") as handle:
            data = handle.read()
        entries[path] = {"oid": oid, "size": len(data),
                         "sha256": hashlib.sha256(data).hexdigest()}
    return entries


class FixtureOwner(cso.NativeInvocationOwner):
    """Inert owner boundary for tests only.  It is constructed here, never
    from request JSON, and it records exactly the invocations it admitted."""

    def __init__(self, host, worktree, git_dir, common_dir, commit, source_paths,
                 observer="observer-1", receiver="receiver-1", alias="fixture-host-alias"):
        self.host = host
        self.worktree = worktree
        self.git_dir = git_dir
        self.common_dir = common_dir
        self.commit = commit
        self.source_paths = tuple(source_paths)
        self.observer = observer
        self.receiver = receiver
        self.alias = alias
        self.revoked = False
        self.publication_allowed = True
        self.active = set()

    def _matches(self, view):
        return (view.host == self.host and view.worktree == self.worktree
                and view.git_dir == self.git_dir and view.common_dir == self.common_dir
                and view.commit == self.commit
                and view.source_paths == self.source_paths
                and view.observer == self.observer
                and view.receiver == self.receiver and not self.revoked)

    def admit_invocation(self, view, invoking_uid):
        return self._matches(view) and invoking_uid == os.getuid()

    def registered(self, invocation):
        self.active.add(invocation.scope_digest)

    def invocation_active(self, invocation):
        return not self.revoked and invocation.scope_digest in self.active

    def authorize_publication(self, invocation):
        if not self.publication_allowed:
            raise cso.NativeRefused("native_publication_refused_by_owner")
        return self.invocation_active(invocation)

    def transport_alias(self, view):
        return self.alias if self._matches(view) else None

    def revoke_all(self):
        self.revoked = True
        self.active.clear()


class Host(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="cso-rollout-")
        cls.base = cls._tmp.name
        cls.repo = build_repo(cls.base, "repo")
        cls.packed_repo = build_repo(cls.base, "packed")
        if sys.platform.startswith("linux"):
            run_git(cls.packed_repo, "repack", "-adq")
            run_git(cls.packed_repo, "prune-packed", "-q")
        cls.tree = tree_of(cls.repo)
        cls.packed_tree = tree_of(cls.packed_repo)
        cls.commit = run_git(cls.repo, "rev-parse", "HEAD")
        cls.packed_commit = run_git(cls.packed_repo, "rev-parse", "HEAD")
        # A real linked worktree over the packed repository: its .git is a
        # gitfile, its git_dir lives under the main .git, and objects are read
        # from the declared common_dir.
        cls.worktree = os.path.join(cls.base, "linked")
        run_git(cls.packed_repo, "worktree", "add", "-q", cls.worktree, "-b", "wt-1")
        cls.wt_commit = cls.packed_commit
        with open(os.path.join(cls.worktree, "from-worktree.txt"), "w") as handle:
            handle.write("committed inside the linked worktree\n")
        run_git(cls.worktree, "add", ".")
        run_git(cls.worktree, "-c", "user.email=t@example.invalid", "-c", "user.name=t",
                "commit", "-q", "-m", "fixture-worktree")
        cls.wt_commit = run_git(cls.worktree, "rev-parse", "HEAD")
        cls.wt_tree = tree_of(cls.worktree)
        with open(os.path.join(cls.worktree, ".git")) as handle:
            cls.wt_gitfile = handle.read()
        cls.wt_git_dir = cls.wt_gitfile.split("gitdir: ", 1)[1].strip()
        with open(os.path.join(cls.wt_git_dir, "commondir")) as handle:
            raw_common = handle.read().strip()
        # Git may write the commondir pointer relative to the git_dir; resolve
        # it lexically exactly as the reader does.
        cls.wt_common_dir = (raw_common if raw_common.startswith("/")
                             else os.path.normpath(
                                 os.path.join(cls.wt_git_dir, raw_common)))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    # -- request/owner builders -------------------------------------------
    def target(self, repo=None):
        repo = repo or self.repo
        if repo == self.worktree:
            return {"worktree": repo, "git_dir": self.wt_git_dir,
                    "common_dir": self.wt_common_dir, "commit": self.wt_commit,
                    "tree": self.wt_tree}
        if repo == self.packed_repo:
            return {"worktree": repo, "git_dir": repo + "/.git",
                    "common_dir": repo + "/.git", "commit": self.packed_commit,
                    "tree": self.packed_tree}
        # Any other owned fixture repository is an ordinary repository.
        return {"worktree": repo, "git_dir": repo + "/.git",
                "common_dir": repo + "/.git",
                "commit": run_git(repo, "rev-parse", "HEAD"),
                "tree": tree_of(repo)}

    def request(self, repo=None, sources=None, limits=None, receiver="receiver-1",
                host="ubuntu2", observer="observer-1", historical=None, **overrides):
        spec = self.target(repo)
        if sources is None:
            sources = [{"path": path, "blob": spec["tree"][path]["oid"],
                        "size": spec["tree"][path]["size"]}
                       for path in sorted(FILES)]
        request = {"schema": cso.SCHEMA_REQUEST, "run_id": "run-current-1",
                   "root": "root-current-1", "observer": observer,
                   "receiver": receiver, "host": host,
                   "worktree": spec["worktree"], "git_dir": spec["git_dir"],
                   "common_dir": spec["common_dir"], "commit": spec["commit"],
                   "sources": sources, "limits": limits or dict(cso.DEFAULT_LIMITS)}
        if historical is not None:
            request["historical"] = historical
        request.update(overrides)
        return request

    def owner(self, repo=None, sources=None, receiver="receiver-1",
              observer="observer-1", host="ubuntu2", alias="fixture-host-alias"):
        spec = self.target(repo)
        if sources is None:
            sources = sorted(FILES)
        return FixtureOwner(host, spec["worktree"], spec["git_dir"],
                            spec["common_dir"], spec["commit"], sources,
                            observer=observer, receiver=receiver, alias=alias)

    def observe(self, request, owner, transport=None):
        """Mint at the fixture-owner boundary, then compose one observation."""
        return cso.observe_current_source(request, self.mint(request, owner),
                                          transport if transport is not None
                                          else in_process_transport())

    def mint(self, request, owner):
        return cso.NativeInvocation.mint(
            cso.NativeInvocationView.of(request, cso.validate_request(request)),
            owner, os.getuid())

    def owner_for_request(self, request, **overrides):
        """An inert owner bound to the request's own declared custody, so a
        refusal exercised here comes from the reader's own pointer checks."""
        return FixtureOwner(request["host"], request["worktree"],
                            request["git_dir"], request["common_dir"],
                            request["commit"],
                            sorted(e["path"] for e in request["sources"]),
                            observer=request["observer"],
                            receiver=request["receiver"], **overrides)

    def assertRefused(self, response, reason, state="ADMITTED"):
        self.assertEqual(response["status"], "REFUSED", response)
        self.assertEqual(response["reason"], reason, response)
        self.assertEqual(response["admission"]["state"], state, response)
        self.assertEqual(response["files"], [], response)


def in_process_transport():
    namespace = {}
    source = cso.generated_reader_source()
    exec(compile(source, "generated_reader.py", "exec"), namespace)
    def send(request):
        out = io.BytesIO()
        code = namespace["main_stream"](io.BytesIO(cso.canonical(request)), out)
        assert code == 0, code
        return out.getvalue()
    return send


def subprocess_transport():
    source = cso.generated_reader_source()
    def send(request):
        result = subprocess.run([sys.executable, "-I", "-S", "-c", source],
                                input=cso.canonical(request),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            raise cso.CurrentSourceError("remote_reader_failed",
                                         result.stderr.decode("utf-8", "replace")[:200])
        return result.stdout
    return send


def make_owner_factory(registry):
    """Registry-bound owner factory mirroring the incumbent CLI boundary: the
    lane-host registry binds transport; current external OS/tool permission
    authorizes the scoped read. Provider modes remain unchanged."""
    try:
        import fabric_task
    except ImportError:
        fabric_task = None
    if fabric_task is not None and hasattr(fabric_task,
                                           "_current_source_owner_factory"):
        return fabric_task._current_source_owner_factory(registry)

    class RegistryOwner(FixtureOwner):
        def __init__(self, digest):
            super().__init__("*", "*", "*", "*", "*", ())
            self.request_sha256 = digest
            self.registry = registry

        def _entry(self, view):
            entry = self.registry.get(view.host) if isinstance(self.registry,
                                                               dict) else None
            if (type(entry) is not dict
                    or "lanes" not in entry.get("roles", [])
                    or not isinstance(entry.get("ssh_alias"), str)):
                return None
            return entry

        def admit_invocation(self, view, invoking_uid):
            if (view.request_sha256 != self.request_sha256 or self.revoked
                    or invoking_uid != os.getuid() or view.observer == view.receiver):
                return False
            return self._entry(view) is not None

        def transport_alias(self, view):
            if view.request_sha256 != self.request_sha256 or self.revoked:
                return None
            entry = self._entry(view)
            return None if entry is None else entry["ssh_alias"]

    return RegistryOwner


class TestChain:
    """Inert exclusive-destination stand-in with the incumbent chain surface."""

    def __init__(self, path):
        os.makedirs(path, exist_ok=True)
        self.path = path
        self.fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)

    def verify(self):
        info = os.fstat(self.fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022:
            raise cso.CurrentSourceError("chain_owner_or_mode")

    def close(self):
        os.close(self.fd)


class InvocationTests(Host):
    def test_missing_invocation_performs_zero_reads(self):
        response = cso.observe_current_source(self.request(), None)
        self.assertRefused(response, "admission_admission_missing",
                           state="ADMISSION_MISSING")

    def test_plain_maps_digests_and_booleans_are_not_admission(self):
        spec = self.target()
        for fake in ({"host": "ubuntu2", "worktree": spec["worktree"]},
                     cso.digest_of(spec), True, False, 7, "receiver-1"):
            response = cso.observe_current_source(self.request(), fake)
            self.assertRefused(response, "admission_admission_invalid",
                               state="ADMISSION_INVALID")

    def test_refusing_owner_refuses_at_the_boundary(self):
        class Refusing(cso.NativeInvocationOwner):
            pass
        with self.assertRaises(cso.NativeRefused):
            self.mint(self.request(), Refusing())
        # An owner may also decline without raising; the boundary still refuses.
        class Declining(cso.NativeInvocationOwner):
            def admit_invocation(self, view, invoking_uid):
                return False
        with self.assertRaises(cso.NativeRefused):
            self.mint(self.request(), Declining())

    def test_untrusted_json_cannot_mint_an_invocation(self):
        spec = self.target()
        payload = json.dumps({"host": "ubuntu2", "worktree": spec["worktree"],
                              "commit": spec["commit"]})
        for view in (json.loads(payload), payload, None):
            with self.assertRaises(cso.NativeRefused):
                cso.NativeInvocation.mint(view, self.owner(), os.getuid())
        with self.assertRaises(cso.NativeRefused):
            cso.NativeInvocation.mint(
                cso.NativeInvocationView.of(self.request(),
                                            cso.validate_request(self.request())),
                object(), os.getuid())

    def test_wrong_receiver_host_observer_and_paths_refused(self):
        # The owner re-checks every correlation fact itself, so a request whose
        # receiver, host, observer or paths differ from the owner's own record
        # is refused at the minting boundary; untrusted JSON cannot mint.
        for field, value in (("receiver", "receiver-2"), ("host", "other-host"),
                             ("observer", "observer-2")):
            with self.assertRaises(cso.NativeRefused):
                self.mint(self.request(**{field: value}), self.owner())
        sources = [{"path": "docs/extra.txt",
                    "blob": self.tree["docs/beta.txt"]["oid"],
                    "size": self.tree["docs/beta.txt"]["size"]}]
        with self.assertRaises(cso.NativeRefused):
            self.mint(self.request(sources=sources), self.owner())
        # A later observe with a stale invocation bound to another request is
        # a scope/caller mismatch, refused without reads.
        invocation = self.mint(self.request(), self.owner())
        response = cso.observe_current_source(
            self.request(receiver="receiver-2"), invocation,
            in_process_transport())
        self.assertRefused(response, "admission_admission_invalid",
                           state="ADMISSION_INVALID")

    def test_scope_caller_mismatch_between_requests_refused(self):
        owner = self.owner()
        first = self.mint(self.request(), owner)
        second_request = self.request(repo=self.packed_repo)
        second = self.mint(second_request, self.owner(repo=self.packed_repo))
        self.assertFalse(first.binds_request(second_request))
        self.assertNotEqual(first.scope_digest, second.scope_digest)

    def test_revocation_blocks_read_and_publication(self):
        owner = self.owner()
        request = self.request()
        invocation = self.mint(request, owner)
        first = cso.observe_current_source(request, invocation,
                                           in_process_transport())
        self.assertEqual(first["status"], "OBSERVED", first)
        owner.revoke_all()
        with self.assertRaises(cso.NativeRefused):
            self.mint(request, owner)
        with tempfile.TemporaryDirectory(prefix="cso-pub-") as dest:
            with self.assertRaises(cso.NativeRefused):
                cso.publish_observation(first, dest, invocation, reserve=TestChain)

    def test_root_and_run_id_stay_outside_admission(self):
        response = self.observe(
            self.request(root="root-other", run_id="run-other"),
            self.owner(), in_process_transport())
        self.assertEqual(response["status"], "OBSERVED", response)
        self.assertEqual(response["receipt"]["root"], "root-other")
        self.assertEqual(response["receipt"]["receiver"], "receiver-1")
        self.assertNotEqual(response["receipt"]["root"],
                            response["receipt"]["receiver"])

    def test_historical_opaque_has_no_meaning(self):
        request = self.request(historical="opaque123")
        response = self.observe(request, self.owner(),
                                              in_process_transport())
        self.assertEqual(response["status"], "OBSERVED", response)
        self.assertNotIn("historical_binding", response)
        self.assertNotIn(b"opaque123", cso.canonical(response))
        self.assertNotIn(b"historical", cso.canonical(response["admission"]))
        self.assertEqual(response["receipt"]["request_sha256"],
                         cso.validate_request(request))


class ObservationTests(Host):
    def test_observed_loose_ordinary_repository(self):
        response = self.observe(self.request(), self.owner(),
                                              in_process_transport())
        self.assertEqual(response["status"], "OBSERVED", response)
        self.assertEqual(response["admission"]["state"], "ADMITTED")
        cso.validate_response(response)
        by_path = {item["path"]: item for item in response["files"]}
        for path, meta in self.tree.items():
            item = by_path[path]
            self.assertEqual(item["status"], "RETRIEVED")
            self.assertEqual(item["object_id"], meta["oid"])
            self.assertEqual(item["object_store"], "loose")
            self.assertEqual(item["bytes"], meta["size"])
            self.assertEqual(item["sha256"], meta["sha256"])
            chain = item["membership"]
            self.assertEqual(chain[0]["component"], "<commit>")
            self.assertEqual(chain[0]["object_id"], self.commit)
            self.assertEqual(chain[-1]["object_id"], meta["oid"])
            for link in chain[1:-1]:
                self.assertEqual(link["kind"], "tree")
        receipt = response["receipt"]
        self.assertEqual(receipt["receiver"], "receiver-1")
        self.assertEqual(receipt["request_sha256"],
                         cso.validate_request(self.request()))
        self.assertEqual(receipt["response_sha256"],
                         cso.digest_of({k: v for k, v in response.items()
                                        if k != "receipt"}))

    @unittest.skipUnless(sys.platform.startswith("linux"), "packed reads require Linux memory limits")
    def test_observed_packed_ordinary_repository_via_cat_file(self):
        response = self.observe(self.request(repo=self.packed_repo),
                                              self.owner(repo=self.packed_repo),
                                              subprocess_transport())
        self.assertEqual(response["status"], "OBSERVED", response)
        cso.validate_response(response)
        stores = {item["object_store"] for item in response["files"]}
        self.assertEqual(stores, {"packed"})
        by_path = {item["path"]: item for item in response["files"]}
        self.assertEqual(by_path["src/alpha.py"]["sha256"],
                         self.packed_tree["src/alpha.py"]["sha256"])

    def test_subprocess_generated_reader_matches_in_process_body(self):
        request = self.request()
        body = cso.observe_remote(request)
        raw = subprocess_transport()(request)
        self.assertEqual(cso.strict_json(raw), body)

    def test_remote_revalidates_the_request_itself(self):
        body = cso.strict_json(
            in_process_transport()(dict(self.request(), commit="short")))
        self.assertEqual(body["status"], "REFUSED", body)
        self.assertEqual(body["reason"], "commit_digest_invalid")
        self.assertIsNone(body["request_sha256"])
        body = cso.strict_json(in_process_transport()(dict(
            self.request(),
            sources=[{"path": "../escape.txt", "blob": "a" * 40, "size": 1}])))
        self.assertEqual(body["status"], "REFUSED", body)
        self.assertEqual(body["reason"], "path_invalid")

    def test_wrong_commit_path_not_in_tree(self):
        # Same repository and commit, but a path the tree does not contain.
        sources = [{"path": "docs/gamma.txt", "blob": "1" * 40, "size": 1}]
        request = self.request(sources=sources)
        response = self.observe(request, self.owner_for_request(request),
                                in_process_transport())
        self.assertRefused(response, "path_not_in_tree")

    def test_wrong_blob_expectation_and_size(self):
        sources = [dict(self.request()["sources"][0], blob="b" * 40)]
        response = self.observe(
            self.request(sources=sources),
            self.owner(sources=[sources[0]["path"]]), in_process_transport())
        self.assertRefused(response, "object_mismatch")
        sized = [dict(self.request()["sources"][0], size=999999)]
        response = self.observe(
            self.request(sources=sized),
            self.owner(sources=[sized[0]["path"]]), in_process_transport())
        self.assertRefused(response, "declared_size_mismatch")

    def test_invalid_loose_shard_refuses_without_git_fallback(self):
        # F-1: Git's cat-file can itself follow a symlinked loose shard, even
        # when the direct no-follow reader would refuse it. Never fall back.
        request = self.request(); owner = self.owner()
        shard = os.path.join(self.repo, ".git", "objects", self.commit[:2])
        outside = os.path.join(self.base, "outside-shard")
        os.rename(shard, outside)
        try:
            for kind in ("symlink", "file"):
                if kind == "symlink":
                    os.symlink(outside, shard)
                else:
                    with open(shard, "wb") as handle:
                        handle.write(b"not a directory")
                try:
                    def spawn(*args, **kwargs):
                        self.fail("invalid shard reached Git fallback")
                    reader = cso.Reader(spawn=spawn)
                    response = self.observe(request, owner,
                        lambda req: cso.canonical(cso.observe_remote(req, reader)))
                    self.assertRefused(response, "loose_custody_invalid")
                    body = cso.strict_json(subprocess_transport()(request))
                    self.assertEqual(body["status"], "REFUSED")
                    self.assertEqual(body["reason"], "loose_custody_invalid")
                finally:
                    os.unlink(shard)
        finally:
            os.rename(outside, shard)

    def test_path_only_request_delivers_exact_bytes_and_git_proofs(self):
        request = self.request(sources=[{"path": "src/alpha.py"}])
        response = self.observe(request, self.owner(sources=["src/alpha.py"]))
        self.assertEqual(response["status"], "OBSERVED", response)
        self.assertEqual(base64.b64decode(response["files"][0]["content_b64"]),
                         FILES["src/alpha.py"])
        cso.validate_response(response)
        altered = copy.deepcopy(response)
        altered["files"][0]["content_b64"] = base64.b64encode(b"wrong bytes").decode()
        altered["files"][0]["bytes"] = len(b"wrong bytes")
        altered["files"][0]["sha256"] = hashlib.sha256(b"wrong bytes").hexdigest()
        altered["receipt"]["response_sha256"] = cso.digest_of(
            {k:v for k,v in altered.items() if k != "receipt"})
        with self.assertRaises(cso.CurrentSourceError):
            cso.validate_response(altered)
        altered = copy.deepcopy(response)
        altered["git_objects"][0]["content_b64"] = base64.b64encode(b"bad").decode()
        altered["git_objects"][0]["bytes"] = 3
        altered["receipt"]["response_sha256"] = cso.digest_of(
            {k:v for k,v in altered.items() if k != "receipt"})
        with self.assertRaises(cso.CurrentSourceError):
            cso.validate_response(altered)

    def test_resealed_remote_budget_is_not_accepted(self):
        request = self.request(limits=dict(cso.DEFAULT_LIMITS, max_bytes_total=1000))
        def send(req):
            body = cso.observe_remote(req)
            body["files"][-1]["remaining_budget"] = 0
            return cso.canonical(body)
        response = self.observe(request, self.owner(), send)
        self.assertNotEqual(response["status"], "OBSERVED")
        self.assertEqual(response["reason"], "remote_budget_invalid")

    def test_non_mapping_request_refuses_without_read(self):
        response = cso.observe_current_source(["invalid"])
        self.assertEqual(response["status"], "REFUSED")
        self.assertEqual(response["reason"], "request_invalid")

    def test_empty_paths_still_prove_commit_and_root_tree(self):
        request = self.request(sources=[])
        response = self.observe(request, self.owner(sources=[]))
        self.assertEqual(response["status"], "OBSERVED", response)
        self.assertEqual(response["files"], [])
        self.assertEqual({x["kind"] for x in response["git_objects"]}, {"commit", "tree"})
        cso.validate_response(response)
        request["commit"] = "0" * 40
        owner = self.owner(sources=[]); owner.commit = request["commit"]
        response = self.observe(request, owner)
        self.assertNotEqual(response["status"], "OBSERVED")



class LinkedWorktreeTests(Host):
    def test_gitfile_pointer_and_commondir_are_proven(self):
        self.assertTrue(self.wt_gitfile.startswith("gitdir: "))
        self.assertEqual(cso._resolve_pointer(
            self.wt_gitfile.split("gitdir: ", 1)[1].strip(),
            [p for p in self.worktree.split("/") if p]), self.wt_git_dir)
        self.assertEqual(self.wt_common_dir, self.packed_repo + "/.git")

    @unittest.skipUnless(sys.platform.startswith("linux"), "packed reads require Linux memory limits")
    def test_observed_packed_linked_worktree(self):
        sources = [{"path": path, "blob": self.wt_tree[path]["oid"],
                    "size": self.wt_tree[path]["size"]}
                   for path in sorted(self.wt_tree)]
        response = self.observe(
            self.request(repo=self.worktree, sources=sources),
            self.owner(repo=self.worktree, sources=sorted(self.wt_tree)),
            in_process_transport())
        self.assertEqual(response["status"], "OBSERVED", response)
        cso.validate_response(response)
        stores = {item["object_store"] for item in response["files"]}
        # The pre-worktree commit is fully packed; the commit made inside the
        # linked worktree left loose objects in the same common store.
        self.assertEqual(stores, {"packed", "loose"})
        by_path = {item["path"]: item for item in response["files"]}
        self.assertEqual(by_path["from-worktree.txt"]["object_id"],
                         self.wt_tree["from-worktree.txt"]["oid"])
        self.assertEqual(by_path["from-worktree.txt"]["object_store"], "loose")
        self.assertEqual(by_path["src/alpha.py"]["object_store"], "packed")

    def test_observed_loose_objects_in_linked_worktree_common_store(self):
        # A commit made inside the linked worktree stores loose objects in the
        # common store; the declared common_dir serves every read.
        response = self.observe(
            self.request(repo=self.worktree,
                         sources=[{"path": "from-worktree.txt",
                                   "blob": self.wt_tree["from-worktree.txt"]["oid"],
                                   "size": self.wt_tree["from-worktree.txt"]["size"]}]),
            self.owner(repo=self.worktree, sources=["from-worktree.txt"]),
            in_process_transport())
        self.assertEqual(response["status"], "OBSERVED", response)
        stores = {item["object_store"] for item in response["files"]}
        self.assertEqual(stores, {"loose"})

    def test_wrong_git_dir_pointer_mismatch(self):
        other = build_repo(self.base, "other")
        request = self.request(repo=self.worktree, git_dir=other + "/.git")
        response = self.observe(request,
                                              self.owner_for_request(request),
                                              in_process_transport())
        self.assertRefused(response, "git_pointer_mismatch")

    def test_wrong_common_dir_refused(self):
        request = self.request(repo=self.worktree,
                               common_dir=self.worktree + "/.git")
        response = self.observe(request,
                                              self.owner_for_request(request),
                                              in_process_transport())
        self.assertRefused(response, "commondir_mismatch")

    def test_ordinary_repo_with_mismatched_common_dir_refused(self):
        request = self.request(common_dir=self.base + "/elsewhere")
        response = self.observe(request,
                                              self.owner_for_request(request),
                                              in_process_transport())
        self.assertRefused(response, "commondir_mismatch")

    def test_gitdir_backlink_mismatch_refused(self):
        backlink = os.path.join(self.wt_git_dir, "gitdir")
        with open(backlink) as handle:
            original = handle.read()
        with open(backlink, "w") as handle:
            handle.write(self.base + "/elsewhere/.git\n")
        try:
            request = self.request(repo=self.worktree)
            response = self.observe(
                request, self.owner_for_request(request), in_process_transport())
            self.assertRefused(response, "gitdir_backlink_mismatch")
        finally:
            with open(backlink, "w") as handle:
                handle.write(original)


class CustodyTests(Host):
    def test_symlink_worktree_component_refused(self):
        link = os.path.join(self.base, "link-to-repo")
        if not os.path.lexists(link):
            os.symlink(self.repo, link)
        request = self.request(worktree=link, git_dir=self.repo + "/.git",
                               common_dir=self.repo + "/.git")
        response = self.observe(request,
                                              self.owner_for_request(request),
                                              in_process_transport())
        self.assertRefused(response, "filesystem_refused")

    def test_escape_paths_refused_before_any_read(self):
        for path in ("../../etc/shadow", "/abs/path", "a/../b", ""):
            with self.assertRaises(cso.CurrentSourceError):
                cso.validate_request(self.request(
                    sources=[{"path": path, "blob": "a" * 40, "size": 1}]))

    def test_alternate_and_promisor_common_stores_refused(self):
        alt_repo = build_repo(self.base, "alts")
        info_dir = os.path.join(alt_repo, ".git", "objects", "info")
        os.makedirs(info_dir, exist_ok=True)
        with open(os.path.join(info_dir, "alternates"), "w") as handle:
            handle.write("/nonexistent/objects\n")
        response = self.observe(self.request(repo=alt_repo),
                                              self.owner(repo=alt_repo),
                                              in_process_transport())
        self.assertRefused(response, "unsafe_object_store")
        os.unlink(os.path.join(info_dir, "alternates"))
        with open(os.path.join(info_dir, "promisor"), "w") as handle:
            handle.write("remote=origin\n")
        response = self.observe(self.request(repo=alt_repo),
                                              self.owner(repo=alt_repo),
                                              in_process_transport())
        self.assertRefused(response, "unsafe_object_store")

    def test_hardlinked_loose_object_refused(self):
        oid = self.tree["src/alpha.py"]["oid"]
        obj = os.path.join(self.repo, ".git", "objects", oid[:2], oid[2:])
        os.link(obj, obj + ".dup")
        self.addCleanup(os.unlink, obj + ".dup")
        sources = [entry for entry in self.request()["sources"]
                   if entry["path"] == "src/alpha.py"]
        response = self.observe(
            self.request(sources=sources),
            self.owner(sources=["src/alpha.py"]), in_process_transport())
        self.assertRefused(response, "leaf_hardlinked")

    def test_custody_changed_during_read(self):
        real_open = os.open
        state = {"count": 0}

        def opener(path, flags, dir_fd=None):
            if path == "objects" and dir_fd is not None:
                state["count"] += 1
                if state["count"] == 2:
                    with open(os.path.join(self.repo, "touched.tmp"), "wb") as handle:
                        handle.write(b"swap")
            return real_open(path, flags, dir_fd=dir_fd)

        self.addCleanup(os.unlink, os.path.join(self.repo, "touched.tmp"))
        reader = cso.Reader(opener=opener)
        response = self.observe(
            self.request(), self.owner(),
            lambda request: cso.canonical(cso.observe_remote(request, reader)))
        self.assertEqual(response["status"], "UNAVAILABLE", response)
        self.assertEqual(response["reason"], "changed_during_read")

    def test_swapped_git_pointer_after_read_refused(self):
        # Swapping the linked worktree's .git pointer during the reads must
        # never yield OBSERVED: the post-read pointer snapshot re-derives the
        # pointer and refuses the run outright.
        gitfile = os.path.join(self.worktree, ".git")
        with open(gitfile) as handle:
            original = handle.read()
        real_open = os.open
        state = {"count": 0}

        def opener(path, flags, dir_fd=None):
            if path == ".git" and dir_fd is not None:
                state["count"] += 1
                if state["count"] >= 2:
                    with open(gitfile, "w") as handle:
                        handle.write("gitdir: /nonexistent/elsewhere\n")
            return real_open(path, flags, dir_fd=dir_fd)

        def restore():
            if os.path.exists(gitfile):
                with open(gitfile, "w") as handle:
                    handle.write(original)

        self.addCleanup(restore)
        reader = cso.Reader(opener=opener)
        request = self.request(repo=self.worktree)
        response = self.observe(
            request, self.owner(repo=self.worktree),
            lambda req: cso.canonical(cso.observe_remote(req, reader)))
        self.assertEqual(response["status"], "REFUSED", response)
        self.assertEqual(response["reason"], "git_pointer_mismatch", response)
        self.assertEqual(response["files"], [])


class CapTests(Host):
    def test_file_and_budget_caps(self):
        tight = dict(cso.DEFAULT_LIMITS, max_file_bytes=4)
        small = [{"path": p, "blob": self.tree[p]["oid"],
                  "size": min(self.tree[p]["size"], 4)} for p in sorted(FILES)]
        response = self.observe(
            self.request(sources=small, limits=tight),
            self.owner(sources=[p for p in sorted(FILES)]), in_process_transport())
        self.assertIn(response["reason"],
                      ("size_limit", "object_size_limit", "object_size_mismatch"),
                      response)
        self.assertEqual(response["files"], [])
        budget = dict(cso.DEFAULT_LIMITS, max_bytes_total=10)
        response = self.observe(self.request(limits=budget),
                                              self.owner(), in_process_transport())
        self.assertIn(response["reason"],
                      ("size_limit", "object_size_limit", "object_size_mismatch",
                       "size_budget_exhausted"))
        self.assertEqual(response["files"], [])

    def test_limits_changed_after_mint_refused(self):
        invocation = self.mint(self.request(), self.owner())
        mutated = self.request(limits=dict(cso.DEFAULT_LIMITS, max_file_bytes=16))
        response = cso.observe_current_source(mutated, invocation,
                                              in_process_transport())
        self.assertRefused(response, "admission_admission_invalid",
                           state="ADMISSION_INVALID")

    def test_response_size_bound(self):
        original = cso.MAX_RESPONSE
        cso.MAX_RESPONSE = 200
        try:
            response = self.observe(self.request(), self.owner(),
                                                  in_process_transport())
        finally:
            cso.MAX_RESPONSE = original
        self.assertRefused(response, "response_limit")

    @unittest.skipUnless(sys.platform.startswith("linux"), "packed reads require Linux memory limits")
    def test_process_deadline_enforced(self):
        # A real inert child, not a communicate-only fake: exercise selector,
        # deadline and process cleanup without a network or provider process.
        def spawn(argv, **kwargs):
            return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"], **kwargs)
        reader = cso.Reader(spawn=spawn)
        limits = dict(cso.DEFAULT_LIMITS, deadline_ms=50)
        request = self.request(repo=self.packed_repo, limits=limits)
        response = self.observe(request, self.owner(repo=self.packed_repo),
            lambda req: cso.canonical(cso.observe_remote(req, reader)))
        self.assertRefused(response, "process_deadline")

    @unittest.skipUnless(sys.platform.startswith("linux"), "packed reads require Linux memory limits")
    def test_packed_child_output_bound_and_cleanup(self):
        children = []
        def spawn(argv, **kwargs):
            proc = subprocess.Popen([sys.executable, "-c",
                "import sys; sys.stdout.buffer.write(b'x' * 8388608); sys.stdout.flush()"], **kwargs)
            children.append(proc)
            return proc
        reader = cso.Reader(spawn=spawn)
        argv = [cso.select_git_binary()] + list(cso.GIT_ARGV_PREFIX) + ["cat-file", "--batch"]
        with self.assertRaisesRegex(cso.CurrentSourceError, "process_output_limit"):
            cso._git_batch(reader, argv, b"x\n", cso.git_environment(self.repo+"/.git"), 3)
        self.assertTrue(children)
        self.assertIsNotNone(children[0].poll())

    def test_pack_store_refuses_symlink_and_promisor(self):
        pack = os.path.join(self.repo, ".git", "objects", "pack")
        name = "pack-" + "a"*40 + ".idx"
        target = os.path.join(self.base, "unrelated")
        with open(target, "wb") as handle:
            handle.write(b"inert fixture")
        os.symlink(target, os.path.join(pack, name))
        try:
            with self.assertRaises(cso.CurrentSourceError):
                cso.packed_identity(cso.Reader(), self.repo + "/.git")
        finally:
            os.unlink(os.path.join(pack, name))
        marker = os.path.join(pack, "pack-" + "a"*40 + ".promisor")
        with open(marker, "wb") as handle:
            handle.write(b"")
        try:
            with self.assertRaisesRegex(cso.CurrentSourceError, "unsafe_pack_store"):
                cso.packed_identity(cso.Reader(), self.repo + "/.git")
        finally:
            os.unlink(marker)

    @unittest.skipIf(sys.platform.startswith("linux"), "Linux has qualified memory cap")
    def test_packed_child_refuses_without_qualified_memory_limit(self):
        with self.assertRaisesRegex(cso.CurrentSourceError, "packed_limits_unavailable"):
            cso._git_batch(cso.Reader(), [], b"", {}, 1)


class SideEffectTests(Host):
    def test_hooks_filters_and_lazy_fetch_impossible(self):
        marker = os.path.join(self.base, "marker-should-not-exist")
        hook = os.path.join(self.repo, ".git", "hooks", "post-commit")
        with open(hook, "w") as handle:
            handle.write("#!/bin/sh\ntouch %s\n" % marker)
        os.chmod(hook, 0o755)
        with open(os.path.join(self.repo, ".gitattributes"), "w") as handle:
            handle.write("*.py filter=sideeffect\n")
        run_git(self.repo, "config", "filter.sideeffect.smudge", "touch %s" % marker)
        run_git(self.repo, "config", "filter.sideeffect.clean", "touch %s" % marker)
        run_git(self.repo, "config", "core.hooksPath", ".git/hooks")
        response = self.observe(self.request(), self.owner(),
                                              in_process_transport())
        self.assertEqual(response["status"], "OBSERVED", response)
        self.assertFalse(os.path.exists(marker), "a hook or filter executed")

    @unittest.skipUnless(sys.platform.startswith("linux"), "packed reads require Linux memory limits")
    def test_environment_and_argv_isolated(self):
        recorded = {}
        real_popen = subprocess.Popen

        def spawn(argv, **kwargs):
            recorded["argv"] = argv
            recorded["env"] = kwargs.get("env")
            recorded["cwd"] = kwargs.get("cwd")
            self.assertEqual(argv[0], GIT)
            self.assertEqual(list(argv[1:3]), list(cso.GIT_ARGV_PREFIX))
            self.assertEqual(argv[3], "cat-file")
            self.assertIn(argv[4], ("--batch", "--batch-check"))
            self.assertNotIn("lazy", " ".join(argv))
            self.assertEqual(kwargs.get("cwd"), "/")
            env = kwargs.get("env") or {}
            self.assertNotIn("FABRIC_TEST_CANARY", env)
            self.assertNotIn("HOME", env)
            self.assertEqual(set(env), {"PATH", "GIT_DIR", "GIT_CONFIG_NOSYSTEM",
                                        "GIT_CONFIG_GLOBAL", "GIT_NO_LAZY_FETCH",
                                        "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0",
                                        "GIT_CONFIG_KEY_1", "GIT_CONFIG_VALUE_1",
                                        "GIT_CONFIG_COUNT", "GIT_TERMINAL_PROMPT",
                                        "GIT_CEILING_DIRECTORIES", "LC_ALL"})
            return real_popen(argv, **kwargs)

        os.environ["FABRIC_TEST_CANARY"] = "must-not-leak"
        try:
            reader = cso.Reader(spawn=spawn)
            response = self.observe(
                self.request(repo=self.packed_repo),
                self.owner(repo=self.packed_repo),
                lambda req: cso.canonical(cso.observe_remote(req, reader)))
            self.assertEqual(response["status"], "OBSERVED", response)
            self.assertTrue(recorded["argv"])
        finally:
            os.environ.pop("FABRIC_TEST_CANARY", None)

    def test_no_census_png_or_shell_tokens_in_source(self):
        with open(MODULE_PATH, "r", encoding="utf-8") as handle:
            source = handle.read()
        for token in ("os.uname", "socket.", "getpwuid", "os.system", "shell=True",
                      "os.popen", "os.execv", "getenv(", "PNG", "png", "IHDR",
                      "SyntheticOwner"):
            self.assertNotIn(token, source)
import shlex



class PublicationTests(Host):
    def observed(self, repo=None):
        request = self.request(repo=repo)
        owner = self.owner(repo=repo)
        invocation = self.mint(request, owner)
        response = cso.observe_current_source(request, invocation,
                                              in_process_transport())
        self.assertEqual(response["status"], "OBSERVED", response)
        return request, owner, invocation, response

    def test_publication_exclusive_duplicate_and_interrupted(self):
        request, owner, invocation, response = self.observed()
        with tempfile.TemporaryDirectory(prefix="cso-pub-") as dest:
            final = cso.publish_observation(response, dest, invocation,
                                            reserve=TestChain)
            self.assertTrue(os.path.isfile(final))
            self.assertEqual(stat.S_IMODE(os.stat(final).st_mode), 0o600)
            with open(final, "rb") as handle:
                self.assertEqual(handle.read(), cso.canonical(response))
            with self.assertRaises(cso.CurrentSourceError) as caught:
                cso.publish_observation(response, dest, invocation,
                                        reserve=TestChain)
            self.assertEqual(caught.exception.reason, "duplicate_destination")

            def exploding(fd):
                os.write(fd, b"{")
                raise RuntimeError("interrupted")

            with self.assertRaises(RuntimeError):
                cso.publish_observation(response, dest, invocation,
                                        reserve=TestChain, writer=exploding)
            self.assertEqual([name for name in os.listdir(dest)
                              if name.startswith(".")], [])
            self.assertEqual([name for name in os.listdir(dest)
                              if not name.startswith(".")],
                             [os.path.basename(final)])

    def test_publication_refuses_resealed_foreign_root_and_run(self):
        request, owner, invocation, response = self.observed()
        for field in ("root", "run_id"):
            altered = copy.deepcopy(response)
            altered[field] = "foreign-value"
            if field == "root":
                altered["receipt"][field] = altered[field]
            altered["receipt"]["response_sha256"] = cso.digest_of(
                {k:v for k,v in altered.items() if k != "receipt"})
            with tempfile.TemporaryDirectory(prefix="cso-pub-") as dest:
                with self.assertRaisesRegex(cso.NativeRefused, "native_scope_caller_mismatch"):
                    cso.publish_observation(altered, dest, invocation, reserve=TestChain)
                self.assertEqual(os.listdir(dest), [])

    def test_publication_refuses_caller_mismatch_owner_refusal_and_tamper(self):
        request, owner, invocation, response = self.observed()
        stranger = self.owner()
        second_invocation = self.mint(self.request(), stranger)
        with tempfile.TemporaryDirectory(prefix="cso-pub-") as dest:
            with self.assertRaises(cso.NativeRefused) as caught:
                cso.publish_observation(response, dest, second_invocation,
                                        reserve=TestChain)
            self.assertEqual(caught.exception.reason, "native_scope_caller_mismatch")
            owner.publication_allowed = False
            with self.assertRaises(cso.NativeRefused) as caught:
                cso.publish_observation(response, dest, invocation,
                                        reserve=TestChain)
            self.assertEqual(caught.exception.reason,
                             "native_publication_refused_by_owner")
        tampered = json.loads(cso.canonical(response).decode())
        tampered["files"][0]["sha256"] = "0" * 64
        with self.assertRaises(cso.CurrentSourceError):
            cso.publish_observation(tampered, self.base, invocation,
                                    reserve=TestChain)

    def test_revocation_between_read_and_final_link_fails_closed(self):
        request, owner, invocation, response = self.observed()

        def revoking(fd):
            os.write(fd, cso.canonical(response))
            owner.revoke_all()

        with tempfile.TemporaryDirectory(prefix="cso-pub-") as dest:
            with self.assertRaises(cso.NativeRefused) as caught:
                cso.publish_observation(response, dest, invocation,
                                        reserve=TestChain, writer=revoking)
            self.assertEqual(caught.exception.reason,
                             "native_scope_revoked_before_publication")
            self.assertEqual(os.listdir(dest), [])

    def test_offline_main_validates_and_refuses_request_shaped_input(self):
        _, _, _, response = self.observed()
        good = subprocess.run([sys.executable, MODULE_PATH],
                              input=cso.canonical(response),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertTrue(json.loads(good.stdout.decode())["validated"])
        bad = subprocess.run([sys.executable, MODULE_PATH],
                             input=cso.canonical(self.request()),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(bad.returncode, 66)
        self.assertIn(b"cli_self_authorize_refused", bad.stderr)


def inert_request_loader(path):
    """Inert bounded request read for composition tests only; the incumbent
    owned-reader path is what production uses and its custody rule refuses
    test /tmp directories by design."""
    with open(path, "rb") as handle:
        return handle.read(cso.MAX_REQUEST + 1)


class CompositionTests(Host):
    def test_native_current_source_receipt_end_to_end_inert(self):
        request = self.request(repo=self.worktree)
        owner = self.owner(repo=self.worktree)
        with tempfile.TemporaryDirectory(prefix="cso-req-") as req_dir:
            request_path = os.path.join(req_dir, "request.json")
            with open(request_path, "wb") as handle:
                handle.write(cso.canonical(request))
            with tempfile.TemporaryDirectory(prefix="cso-dest-") as dest:
                summary = cso.native_current_source_receipt(
                    request_path, dest, lambda digest: owner,
                    transport=in_process_transport(), reserve=TestChain,
                    load_request=inert_request_loader)
                self.assertEqual(summary["state"], "PUBLISHED", summary)
                published = summary["destination"]
                with open(published, "rb") as handle:
                    stored = json.loads(handle.read().decode())
                self.assertEqual(stored["receipt"]["receiver"], "receiver-1")
                self.assertEqual(stored["receipt"]["root"], "root-current-1")
                self.assertEqual(stored["receipt"]["no_claims"],
                                 list(cso.NO_CLAIMS))
                cso.validate_response(stored)

    def test_existing_destination_refuses_before_transport(self):
        request = self.request(); owner = self.owner()
        with tempfile.TemporaryDirectory(prefix="cso-req-") as req_dir:
            request_path = os.path.join(req_dir, "request.json")
            with open(request_path, "wb") as handle:
                handle.write(cso.canonical(request))
            def reserve(_):
                raise cso.CurrentSourceError("duplicate_destination")
            def send(_):
                self.fail("duplicate destination reached transport")
            with self.assertRaisesRegex(cso.CurrentSourceError, "duplicate_destination"):
                cso.native_current_source_receipt(request_path, req_dir,
                    lambda digest: owner, transport=send, reserve=reserve,
                    load_request=inert_request_loader)

    def test_owner_without_alias_refuses_transport(self):
        request = self.request()
        owner = self.owner()
        owner.alias = None
        with tempfile.TemporaryDirectory(prefix="cso-req-") as req_dir:
            request_path = os.path.join(req_dir, "request.json")
            with open(request_path, "wb") as handle:
                handle.write(cso.canonical(request))
            with tempfile.TemporaryDirectory(prefix="cso-dest-") as dest:
                with self.assertRaises(cso.NativeRefused):
                    cso.native_current_source_receipt(
                        request_path, dest, lambda digest: owner,
                        reserve=TestChain, load_request=inert_request_loader)


class CliTests(Host):
    def test_fabric_task_wiring_requires_registered_lane_host(self):
        try:
            import fabric_task  # noqa: F401  (incumbent CLI under test)
        except ImportError as exc:
            self.skipTest("incumbent fabric_task dependencies unavailable: %s"
                          % exc)
        import artifact_delivery
        # A transport entry without the registered lane role is insufficient.
        # Provider allowed_modes are preserved and are never read grants.
        registry = {"ubuntu2": {"allowed_modes": ["glm"], "ssh_alias": "hostalias"}}
        from fabric_task import _current_source_owner_factory
        factory = _current_source_owner_factory(registry)
        request = self.request()
        digest = cso.validate_request(request)
        bound = factory(digest)
        self.assertFalse(bound.admit_invocation(
            cso.NativeInvocationView.of(request, digest), os.getuid()))
        registered = _current_source_owner_factory(
            {"ubuntu2": {"roles": ["lanes"], "allowed_modes": ["glm"],
                         "ssh_alias": "hostalias"}})(digest)
        with mock.patch.dict(os.environ, CODEX_THREAD_ID=request["observer"]):
            self.assertTrue(registered.admit_invocation(
                cso.NativeInvocationView.of(request, digest), os.getuid()))
        self.assertEqual(registered.transport_alias(
            cso.NativeInvocationView.of(request, digest)), "hostalias")
        self.assertIsNone(bound.transport_alias(
            cso.NativeInvocationView.of(request, digest)))
        # Wrong uid refused even for a registered lane host.
        self.assertFalse(registered.admit_invocation(
            cso.NativeInvocationView.of(request, digest), os.getuid() + 1))

    def test_source_route_preserves_provider_registry_enum(self):
        import fabric_task
        from host_pick import MODE_TOOLS
        request = self.request(); digest = cso.validate_request(request)
        registry = {"ubuntu2": {"roles": ["lanes"], "allowed_modes": ["glm"],
                                "ssh_alias": "hostalias"}}
        original = copy.deepcopy(registry)
        with mock.patch.dict(os.environ, CODEX_THREAD_ID=request["observer"]):
            owner = fabric_task._current_source_owner_factory(registry)(digest)
            self.assertTrue(owner.admit_invocation(cso.NativeInvocationView.of(request, digest), os.getuid()))
            self.assertEqual(registry, original)
            self.assertTrue(all(mode in MODE_TOOLS for mode in registry["ubuntu2"]["allowed_modes"]))
            invalid = copy.deepcopy(registry)
            invalid["ubuntu2"]["allowed_modes"].append("current-source")
            owner = fabric_task._current_source_owner_factory(invalid)(digest)
            self.assertFalse(owner.admit_invocation(cso.NativeInvocationView.of(request, digest), os.getuid()))

    def test_fabric_task_current_source_cli_end_to_end(self):
        try:
            import fabric_task
            import artifact_delivery
        except ImportError as exc:
            self.skipTest("incumbent fabric_task dependencies unavailable: %s"
                          % exc)
        request = self.request(repo=self.worktree)
        owner = self.owner(repo=self.worktree)
        real_popen = artifact_delivery.subprocess.Popen

        def mocked_ssh(argv, **kwargs):
            self.assertEqual(argv[0], "ssh")
            self.assertEqual(argv[1:7],
                             ["-o", "BatchMode=yes",
                              "-o", "StrictHostKeyChecking=yes",
                              "-o", "ConnectTimeout=8"])
            alias, command = argv[7], argv[8]
            self.assertEqual(alias, "fixture-host-alias")
            prefix = "python3 -I -S -c "
            self.assertTrue(command.startswith(prefix), command[:80])
            tokens = shlex.split(command)
            self.assertEqual(tokens[:4], ["python3", "-I", "-S", "-c"])
            code = tokens[4]
            self.assertNotIn(cso.canonical(request).decode("ascii"), command)
            self.assertEqual(code, cso.generated_reader_source())
            return real_popen([sys.executable, "-I", "-S", "-c", code], **kwargs)

        with tempfile.TemporaryDirectory(prefix="cso-req-") as req_dir:
            request_path = os.path.join(req_dir, "request.json")
            with open(request_path, "wb") as handle:
                handle.write(cso.canonical(request))
            registry = {"ubuntu2": {"roles": ["lanes"], "allowed_modes": ["glm"],
                                    "ssh_alias": "fixture-host-alias"}}
            captured = {}

            def factory(digest):
                captured["owner"] = fabric_task._current_source_owner_factory(
                    registry)(digest)
                return captured["owner"]

            artifact_delivery.subprocess.Popen = mocked_ssh
            try:
                with tempfile.TemporaryDirectory(prefix="cso-dest-") as dest:
                    with mock.patch.dict(os.environ, CODEX_THREAD_ID=request["observer"]):
                        summary = fabric_task.current_source_flow(
                            request_path, dest, factory, reserve=TestChain,
                            load_request=inert_request_loader)
            finally:
                artifact_delivery.subprocess.Popen = real_popen
            self.assertEqual(summary["state"], "PUBLISHED", summary)
            self.assertEqual(summary["receipt"]["receiver"], "receiver-1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
