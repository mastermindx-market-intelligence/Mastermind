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


# The exact eight relative source paths of this repair.  Three of them sit
# under "__tests__", a component the previous first-character class refused,
# so an all-eight request is the discriminator for the leading-underscore
# component admission.
UNDERSCORE_PATHS = (
    "terminal/lib/__tests__/visualIntelligenceEvidence.test.ts",
    "terminal/app/api/portfolio/risk-history/route.ts",
    "terminal/lib/portfolioRiskHistory.ts",
    "terminal/lib/__tests__/portfolioRiskHistoryRoute.test.ts",
    "terminal/lib/__tests__/portfolioRiskHistory.test.ts",
    "terminal/lib/portfolio.ts",
    "terminal/lib/portfolioSnapshot.server.ts",
    "terminal/docs/pr-crops/b-f08-9-risk-history/EVIDENCE.yml",
)

# Synthetic harmless bytes committed at each exact path inside the owned
# fixture repositories; every read must bind these exact bytes.
UNDERSCORE_BYTES = {
    "terminal/lib/__tests__/visualIntelligenceEvidence.test.ts":
        b"describe('visualIntelligenceEvidence fixture', () => {\n"
        b"  it('synthetic inert bytes', () => {});\n"
        b"});\n",
    "terminal/app/api/portfolio/risk-history/route.ts":
        b"export const runtime = 'fixture';\n",
    "terminal/lib/portfolioRiskHistory.ts":
        b"export const RISK_HISTORY_FIXTURE = 'risk-history-synthetic-bytes';\n",
    "terminal/lib/__tests__/portfolioRiskHistoryRoute.test.ts":
        b"it('route fixture', () => expect(true).toBe(true));\n",
    "terminal/lib/__tests__/portfolioRiskHistory.test.ts":
        b"it('history fixture', () => expect(true).toBe(true));\n",
    "terminal/lib/portfolio.ts":
        b"export const PORTFOLIO_FIXTURE = 1;\n",
    "terminal/lib/portfolioSnapshot.server.ts":
        b"export const SNAPSHOT_FIXTURE = 'server-synthetic';\n",
    "terminal/docs/pr-crops/b-f08-9-risk-history/EVIDENCE.yml":
        b"fixture: risk-history-evidence\nstatus: synthetic\n",
}


def build_eight_path_repo(root: str, name: str) -> str:
    """Owned synthetic repository committing the exact eight paths with the
    exact bytes above, so observations bind real Git OIDs and real bytes."""
    repo = os.path.join(root, name)
    os.makedirs(repo)
    run_git(repo, "init", "-q", "-b", "main", ".")
    for path, data in UNDERSCORE_BYTES.items():
        target = os.path.join(repo, path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(data)
    run_git(repo, "add", ".")
    run_git(repo, "-c", "user.email=t@example.invalid", "-c", "user.name=t",
            "commit", "-q", "-m", "fixture-underscore-components")
    return repo


class FixtureOwner(cso.NativeInvocationOwner):
    """Inert owner boundary for tests only.  It is constructed here, never
    from request JSON, and it records exactly the invocations it admitted."""

    def __init__(self, host, worktree, git_dir, common_dir, commit, source_paths,
                 observer="observer-1", receiver="receiver-1", alias="fixture-host-alias",
                 custody=None):
        self.host = host
        self.worktree = worktree
        self.git_dir = git_dir
        self.common_dir = common_dir
        self.custody = custody
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
                and view.custody == self.custody
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

    def custody_request(self, repo=None, sources=None, boundary=None, **overrides):
        """The additive resolution variant: no git_dir/common_dir, the whole
        custody dict instead, bounded by an absolute non-root boundary that
        strictly contains the exact worktree."""
        spec = self.target(repo)
        request = self.request(repo=repo, sources=sources, **overrides)
        request.pop("git_dir")
        request.pop("common_dir")
        request["custody"] = {"mode": cso.CUSTODY_MODE,
                              "boundary": self.base if boundary is None else boundary}
        return request

    def custody_owner(self, request, **overrides):
        """An inert owner bound to the request's own custody dict; the scope
        carries the declared boundary and mode, never preknown resolved
        paths."""
        return FixtureOwner(request["host"], request["worktree"], None, None,
                            request["commit"],
                            sorted(e["path"] for e in request["sources"]),
                            observer=request["observer"],
                            receiver=request["receiver"],
                            custody=request["custody"], **overrides)

    def custody_request_for(self, worktree, boundary=None, sources=None,
                            commit=None):
        """Custody request for an arbitrary worktree path -- including paths
        that are not functional checkouts, whose tree must not be derived."""
        request = self.request(sources=sources if sources is not None else [])
        request["worktree"] = worktree
        request.pop("git_dir")
        request.pop("common_dir")
        request["custody"] = {"mode": cso.CUSTODY_MODE,
                              "boundary": self.base if boundary is None else boundary}
        if commit is not None:
            request["commit"] = commit
        return request

    def eight_fixture(self):
        """Owned eight-path fixture, built at most once per test: an ordinary
        repository with the exact eight relative paths committed, plus a real
        linked worktree over the same store for the custody variant."""
        if not hasattr(self, "_eight"):
            suffix = self.id().rsplit(".", 1)[-1]
            repo = build_eight_path_repo(self.base, "underscore-" + suffix)
            linked = os.path.join(self.base, "underscore-linked-" + suffix)
            run_git(repo, "worktree", "add", "-q", linked, "-b", "wt-u")
            self._eight = {"repo": repo, "linked": linked,
                           "commit": run_git(repo, "rev-parse", "HEAD"),
                           "tree": tree_of(repo)}
        return self._eight

    def eight_sources(self, tree=None):
        """All eight entries with their actual Git OIDs and exact sizes, in
        the fixed path order; eight entries sit exactly at MAX_SOURCES."""
        tree = tree if tree is not None else self.eight_fixture()["tree"]
        return [{"path": path, "blob": tree[path]["oid"],
                 "size": tree[path]["size"]} for path in UNDERSCORE_PATHS]

    def eight_request(self, linked=False):
        """An explicit-triple request (or the custody variant over the real
        linked worktree) carrying all eight exact paths."""
        fixture = self.eight_fixture()
        if linked:
            request = self.request(sources=self.eight_sources(),
                                   commit=fixture["commit"])
            request["worktree"] = fixture["linked"]
            request.pop("git_dir")
            request.pop("common_dir")
            request["custody"] = {"mode": cso.CUSTODY_MODE,
                                  "boundary": self.base}
            return request
        return self.request(repo=fixture["repo"],
                            sources=self.eight_sources())

    def owner_bound(self, request, **overrides):
        """An inert owner bound to this exact request: its declared custody
        (triple or resolution variant) and its exact source order."""
        return FixtureOwner(request["host"], request["worktree"],
                            request.get("git_dir"), request.get("common_dir"),
                            request["commit"],
                            [e["path"] for e in request["sources"]],
                            observer=request["observer"],
                            receiver=request["receiver"],
                            custody=request.get("custody"), **overrides)

    def assertEightPathsBound(self, request, response, root_tree_oid=None):
        """The delivered body binds the original request and every one of the
        eight requested blobs: exact bytes, exact Git OIDs, exact membership
        chains and the exact root tree."""
        self.assertEqual(response["status"], "OBSERVED", response)
        self.assertEqual(response["schema"], cso.SCHEMA_OBSERVATION)
        self.assertEqual(response["request_sha256"], cso.validate_request(request))
        self.assertEqual(response["run_id"], request["run_id"])
        self.assertEqual(response["root"], request["root"])
        self.assertEqual(response["observer"], request["observer"])
        self.assertEqual(response["receiver"], request["receiver"])
        self.assertEqual(response["host"], request["host"])
        self.assertEqual(response["commit"], request["commit"])
        self.assertEqual(response["worktree"], request["worktree"])
        files = response["files"]
        self.assertEqual(len(files), 8)
        self.assertEqual([item["path"] for item in files],
                         list(UNDERSCORE_PATHS))
        for entry, item in zip(request["sources"], files):
            self.assertEqual(item["kind"], "source")
            self.assertEqual(item["status"], "RETRIEVED")
            data = base64.b64decode(item["content_b64"], validate=True)
            self.assertEqual(data, UNDERSCORE_BYTES[item["path"]])
            self.assertEqual(item["bytes"], len(data))
            self.assertEqual(item["bytes"], entry["size"])
            self.assertEqual(hashlib.sha256(data).hexdigest(), item["sha256"])
            self.assertEqual(item["object_id"], entry["blob"])
            self.assertIn(item["object_store"], ("loose", "packed"))
            self.assertEqual(item["remaining_budget"],
                             cso.MAX_BYTES_TOTAL - sum(
                                 len(UNDERSCORE_BYTES[p]) for p in
                                 UNDERSCORE_PATHS[:UNDERSCORE_PATHS.index(
                                     item["path"]) + 1]))
            membership = item["membership"]
            self.assertEqual(membership[0], {"component": "<commit>",
                                             "kind": "commit",
                                             "object_id": request["commit"]})
            self.assertEqual([link["component"] for link in membership[1:]],
                             item["path"].split("/"))
            self.assertTrue(all(link["kind"] == "tree" for link in membership[1:-1]))
            self.assertEqual(membership[-1]["kind"], "blob")
            self.assertEqual(membership[-1]["object_id"], entry["blob"])
        proven = {row["object_id"] for row in response["git_objects"]}
        self.assertLessEqual({"commit", "tree"},
                             {row["kind"] for row in response["git_objects"]})
        if root_tree_oid is not None:
            self.assertIn(root_tree_oid, proven)
        self.assertTrue(cso.SHA1.fullmatch(request["commit"]))
        return files

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
        try:
            import fabric_task
        except ImportError as exc:
            self.skipTest("incumbent fabric_task dependencies unavailable: %s"
                          % exc)
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


class CustodyResolutionTests(Host):
    """The additive worktree_pointer_graph custody variant: finite resolution
    inside a declared boundary, bounded proof in the response, and refusal of
    every escape, mixed or mutated shape.  All fixtures are real Git
    repositories and real linked worktrees created inside the owned temp
    directory; no scan, upward walk or Git discovery ever resolves them."""

    def refusing_transport(self):
        def send(_request):
            self.fail("a refused or unresolved request reached the transport")
        return send

    def decode(self, entry):
        return base64.b64decode(entry["bytes_b64"], validate=True)

    # -- valid resolutions -------------------------------------------------
    def test_ordinary_repository_resolves_directory_git(self):
        request = self.custody_request()
        response = self.observe(request, self.custody_owner(request),
                                in_process_transport())
        self.assertEqual(response["status"], "OBSERVED", response)
        cso.validate_response(response)
        self.assertEqual(response["git_dir"], self.repo + "/.git")
        self.assertEqual(response["common_dir"], self.repo + "/.git")
        self.assertEqual(response["custody"], request["custody"])
        proof = response["resolution"]
        self.assertEqual(proof["mode"], cso.CUSTODY_MODE)
        self.assertEqual(proof["boundary"], self.base)
        self.assertEqual(proof["git_link"],
                         {"kind": "dir", "bytes_b64": None, "identity": None})
        self.assertEqual(proof["commondir"], {"bytes_b64": None, "identity": None})
        self.assertEqual(proof["gitdir_backlink"], {"bytes_b64": None, "identity": None})
        self.assertEqual(proof["dir_ids"]["git_dir"], proof["dir_ids"]["common_dir"])
        by_path = {item["path"]: item for item in response["files"]}
        self.assertEqual(by_path["src/alpha.py"]["object_store"], "loose")
        self.assertEqual(by_path["src/alpha.py"]["sha256"],
                         self.tree["src/alpha.py"]["sha256"])
        # Sealed to the exact request digest, which binds the whole custody
        # dict, and to observer/root/receiver/host/commit.
        self.assertEqual(response["receipt"]["request_sha256"],
                         cso.validate_request(request))
        self.assertEqual(response["receipt"]["commit"], request["commit"])
        self.assertEqual(response["receipt"]["receiver"], "receiver-1")

    def test_linked_worktree_absolute_gitfile_relative_commondir_resolves(self):
        # A real `git worktree add` graph: absolute gitfile pointer, relative
        # `../..` commondir pointer, absolute worktree/.git backlink.
        self.assertTrue(self.wt_gitfile.startswith("gitdir: /"))
        with open(os.path.join(self.wt_git_dir, "commondir")) as handle:
            self.assertEqual(handle.read().strip(), "../..")
        sources = [{"path": path, "blob": self.wt_tree[path]["oid"],
                    "size": self.wt_tree[path]["size"]}
                   for path in sorted(self.wt_tree)]
        request = self.custody_request(repo=self.worktree, sources=sources)
        response = self.observe(request,
                                self.custody_owner(request),
                                in_process_transport())
        self.assertEqual(response["status"], "OBSERVED", response)
        cso.validate_response(response)
        self.assertEqual(response["git_dir"], self.wt_git_dir)
        self.assertEqual(response["common_dir"], self.wt_common_dir)
        proof = response["resolution"]
        self.assertEqual(proof["git_link"]["kind"], "file")
        self.assertEqual(self.decode(proof["git_link"]).decode(), self.wt_gitfile)
        self.assertEqual(len(proof["git_link"]["identity"]), 8)
        self.assertEqual(self.decode(proof["commondir"]).decode().strip(), "../..")
        self.assertEqual(self.decode(proof["gitdir_backlink"]).decode().strip(),
                         self.worktree + "/.git")
        # Standard linked shape: git_dir = common/worktrees/<one component>.
        self.assertTrue(response["git_dir"].startswith(response["common_dir"]
                                                      + "/worktrees/"))
        self.assertEqual(len(response["git_dir"].split("/worktrees/", 1)[1].split("/")),
                         1)
        stores = {item["object_store"] for item in response["files"]}
        # Host repacks the shared store only on Linux (the qualified RLIMIT_AS
        # path); elsewhere every object stays loose, so the expected stores
        # follow the platform instead of assuming packed+loose everywhere.
        self.assertEqual(stores, {"packed", "loose"}
                         if sys.platform.startswith("linux") else {"loose"})

    def test_relative_gitfile_pointer_normalizes_within_boundary(self):
        rel_wt = os.path.join(self.base, "linked-rel")
        run_git(self.packed_repo, "worktree", "add", "-q", rel_wt, "-b", "wt-rel")
        expected_git_dir = os.path.join(self.packed_repo, ".git", "worktrees",
                                        "linked-rel")
        with open(os.path.join(rel_wt, ".git"), "w") as handle:
            handle.write("gitdir: ../packed/.git/worktrees/linked-rel\n")
        request = self.custody_request(repo=rel_wt)
        response = self.observe(request, self.custody_owner(request),
                                in_process_transport())
        self.assertEqual(response["status"], "OBSERVED", response)
        cso.validate_response(response)
        self.assertEqual(response["git_dir"], expected_git_dir)
        self.assertEqual(response["common_dir"], self.packed_repo + "/.git")
        self.assertEqual(self.decode(response["resolution"]["git_link"]).decode(),
                         "gitdir: ../packed/.git/worktrees/linked-rel\n")

    # -- variant and boundary refusals, all before any read ----------------
    def test_mixed_and_unknown_custody_variants_refused_before_read(self):
        transport = self.refusing_transport()
        def variant(custody, **overrides):
            request = self.custody_request(**overrides)
            if custody is None:
                request.pop("custody")
            else:
                request["custody"] = custody
            return request
        mixed = self.custody_request()
        mixed["git_dir"] = self.repo + "/.git"
        partial = {"mode": cso.CUSTODY_MODE}
        extra = {"mode": cso.CUSTODY_MODE, "boundary": self.base, "scope": "x"}
        for request, reason in (
                (mixed, "custody_variant_invalid"),
                (variant(partial), "custody_variant_invalid"),
                (variant(extra), "custody_variant_invalid"),
                (variant({"mode": "declared_trust_me", "boundary": self.base}),
                 "custody_variant_invalid"),
                (variant({"mode": None, "boundary": self.base}),
                 "custody_variant_invalid"),
                (variant({"mode": cso.CUSTODY_MODE, "boundary": "relative/path"}),
                 "custody_path_invalid")):
            with self.subTest(reason=reason, request=sorted(request)):
                response = cso.observe_current_source(request, None, transport)
                self.assertRefused(response, reason, state="NOT_SEEKED")

    def test_boundary_relationships_refused_before_read(self):
        transport = self.refusing_transport()
        cases = [(self.custody_request(boundary="/"), "custody_path_invalid"),
                 (self.custody_request(boundary=self.repo), "custody_boundary_invalid"),
                 (self.custody_request(boundary=self.worktree),
                  "custody_boundary_invalid"),
                 (self.custody_request(boundary=self.base + "/unrelated/other"),
                  "custody_boundary_invalid"),
                 (self.custody_request(boundary=self.base + "/" + os.path.basename(
                     self.repo) + "/nested"), "custody_boundary_invalid")]
        for request, reason in cases:
            with self.subTest(reason=reason):
                response = cso.observe_current_source(request, None, transport)
                self.assertRefused(response, reason, state="NOT_SEEKED")

    def test_scope_binds_custody_and_refuses_other_boundary(self):
        request = self.custody_request(repo=self.worktree)
        invocation = self.mint(request, self.custody_owner(request))
        elsewhere = self.custody_request(
            repo=self.worktree,
            sources=[{"path": "docs/beta.txt"}])
        response = cso.observe_current_source(elsewhere, invocation,
                                              self.refusing_transport())
        self.assertRefused(response, "admission_admission_invalid",
                           state="ADMISSION_INVALID")
        # The same scope never admits the explicit triple shape either.
        response = cso.observe_current_source(self.request(repo=self.worktree),
                                              invocation, self.refusing_transport())
        self.assertRefused(response, "admission_admission_invalid",
                           state="ADMISSION_INVALID")

    # -- frozen custody state ----------------------------------------------
    def test_frozen_custody_survives_request_and_property_mutation(self):
        # The view and the minted scope freeze the declared (mode, boundary)
        # pair: mutating the caller's live request dict -- or the mapping the
        # property hands back -- must not move binding(), scope_digest or the
        # admitted scope.
        request = self.custody_request(repo=self.worktree)
        view = cso.NativeInvocationView.of(request, cso.validate_request(request))
        owner = self.custody_owner(request)
        invocation = cso.NativeInvocation.mint(view, owner, os.getuid())
        original = copy.deepcopy(request["custody"])
        binding = view.binding()
        scope_digest = invocation.scope_digest
        # Mutate the caller's request dict in place, then tear it further.
        request["custody"]["boundary"] = "/forged/elsewhere"
        request["custody"]["mode"] = "mutated"
        self.assertEqual(view.custody, original)
        self.assertEqual(view.binding(), binding)
        self.assertEqual(invocation.custody, original)
        self.assertEqual(invocation.scope_digest, scope_digest)
        self.assertFalse(invocation.binds_request(request))
        request["custody"].pop("boundary")
        self.assertEqual(view.custody, original)
        self.assertEqual(view.binding(), binding)
        self.assertEqual(invocation.scope_digest, scope_digest)
        # Mutating the defensive property return is equally inert.
        request["custody"] = dict(original)
        returned = invocation.custody
        returned["boundary"] = "/forged/other"
        returned["mode"] = "other-mode"
        self.assertEqual(invocation.custody, original)
        self.assertEqual(view.custody, original)
        self.assertEqual(view.binding(), binding)
        self.assertEqual(invocation.scope_digest, scope_digest)
        # The unmutated request still binds, so nothing else moved.
        self.assertTrue(invocation.binds_request(request))

    def test_forged_changed_boundary_cannot_publish_after_request_mutation(self):
        # Retargeting the caller's live request dict after mint must not
        # retarget the admitted scope: a body made fully self-consistent with
        # the NEW boundary still refuses publication, while the honest body
        # keeps publishing under the same scope.  The observation runs under
        # the very invocation used for publication, so the refusal below can
        # only come from the custody binding itself.
        request = self.custody_request(repo=self.worktree)
        owner = self.custody_owner(request)
        invocation = self.mint(request, owner)
        observed = cso.observe_current_source(request, invocation,
                                              in_process_transport())
        self.assertEqual(observed["status"], "OBSERVED", observed)
        self.assertEqual(observed["admission"]["scope_digest"],
                         invocation.scope_digest)
        other_boundary = os.path.dirname(self.base)
        self.assertNotEqual(other_boundary, "/")
        self.assertTrue(self.base.startswith(other_boundary + "/"))
        self.assertNotEqual(other_boundary, request["custody"]["boundary"])
        request["custody"]["boundary"] = other_boundary
        forged = copy.deepcopy(observed)
        forged["custody"] = dict(request["custody"])
        forged["resolution"] = copy.deepcopy(observed["resolution"])
        forged["resolution"]["boundary"] = other_boundary
        forged["receipt"]["response_sha256"] = cso.digest_of(
            {k: v for k, v in forged.items() if k != "receipt"})
        cso.validate_response(forged)
        with tempfile.TemporaryDirectory(prefix="custody-frozen-") as dest:
            with self.assertRaisesRegex(cso.NativeRefused,
                                        "native_scope_caller_mismatch"):
                cso.publish_observation(forged, dest, invocation, reserve=TestChain)
            self.assertEqual(os.listdir(dest), [])
        with tempfile.TemporaryDirectory(prefix="custody-honest-") as dest:
            final = cso.publish_observation(observed, dest, invocation,
                                            reserve=TestChain)
            self.assertTrue(final.startswith(dest + "/"))
            self.assertEqual(len(os.listdir(dest)), 1)

    # -- pointer graph refusals -------------------------------------------
    def test_pointer_escape_outside_boundary_refused(self):
        outside = build_repo(self.base, "outside")
        bound = os.path.join(self.base, "bound")
        os.makedirs(bound, exist_ok=True)
        run_git(outside, "worktree", "add", "-q", os.path.join(bound, "wt"),
                "-b", "wt-out")
        escaped_worktree = os.path.join(bound, "wt")
        request = self.custody_request(repo=escaped_worktree, boundary=bound)
        self.assertTrue(request["worktree"].startswith(bound + "/"))
        response = self.observe(request, self.custody_owner(request),
                                in_process_transport())
        self.assertRefused(response, "custody_resolution_invalid")
        # A lexical ../.. escape is refused by containment alone: the target
        # does not even exist, so no walk could have produced the refusal.
        escaped = self.custody_request(repo=escaped_worktree, boundary=bound)
        with open(os.path.join(escaped_worktree, ".git"), "w") as handle:
            handle.write("gitdir: ../../outside-escape/.git\n")
        response = self.observe(escaped, self.custody_owner(escaped),
                                in_process_transport())
        self.assertRefused(response, "custody_resolution_invalid")

    def test_relocated_separate_gitdir_refused(self):
        relocated = os.path.join(self.base, "relocated-git")
        worktree = os.path.join(self.base, "relocated-wt")
        run_git(self.base, "init", "-q", "-b", "main", "--separate-git-dir",
                relocated, worktree)
        with open(os.path.join(worktree, ".git")) as handle:
            self.assertTrue(handle.read().startswith("gitdir: "))
        self.assertFalse(os.path.exists(os.path.join(relocated, "commondir")))
        request = self.custody_request_for(worktree, commit=self.commit)
        response = self.observe(request, self.custody_owner(request),
                                in_process_transport())
        self.assertRefused(response, "custody_resolution_invalid")

    def test_nonstandard_linked_shape_refused(self):
        common_repo = build_repo(self.base, "shape-common")
        shape_git = os.path.join(self.base, "shape-git")
        os.makedirs(shape_git)
        with open(os.path.join(shape_git, "commondir"), "w") as handle:
            handle.write(common_repo + "/.git\n")
        worktree = os.path.join(self.base, "shape-wt")
        os.makedirs(worktree)
        with open(os.path.join(worktree, ".git"), "w") as handle:
            handle.write("gitdir: " + shape_git + "\n")
        request = self.custody_request_for(worktree, commit=self.commit)
        response = self.observe(request, self.custody_owner(request),
                                in_process_transport())
        self.assertRefused(response, "custody_resolution_invalid")

    def test_wrong_and_missing_backlink_refused(self):
        backlink = os.path.join(self.wt_git_dir, "gitdir")
        with open(backlink) as handle:
            original = handle.read()
        def restore():
            with open(backlink, "w") as handle:
                handle.write(original)
        self.addCleanup(restore)
        with open(backlink, "w") as handle:
            handle.write(self.base + "/elsewhere/.git\n")
        request = self.custody_request(repo=self.worktree)
        response = self.observe(request, self.custody_owner(request),
                                in_process_transport())
        self.assertRefused(response, "gitdir_backlink_mismatch")
        os.unlink(backlink)
        missing = self.custody_request(repo=self.worktree)
        response = self.observe(missing, self.custody_owner(missing),
                                in_process_transport())
        self.assertRefused(response, "gitdir_backlink_mismatch")

    def test_malformed_multiline_and_oversize_pointers_refused(self):
        gitfile = os.path.join(self.worktree, ".git")
        with open(gitfile) as handle:
            original = handle.read()
        def restore():
            with open(gitfile, "w") as handle:
                handle.write(original)
        self.addCleanup(restore)
        for payload, reason in (
                ("gitdir: %s\nextra line\n" % self.wt_git_dir, "git_pointer_invalid"),
                ("GITDIR: %s\n" % self.wt_git_dir, "git_pointer_invalid"),
                ("gitdir: \n", "git_pointer_invalid"),
                ("gitdir: " + "x" * 5000 + "\n", "size_limit")):
            with self.subTest(reason=reason):
                with open(gitfile, "w") as handle:
                    handle.write(payload)
                request = self.custody_request(repo=self.worktree)
                response = self.observe(request, self.custody_owner(request),
                                        in_process_transport())
                self.assertRefused(response, reason)
        restore()
        commondir = os.path.join(self.wt_git_dir, "commondir")
        with open(commondir) as handle:
            original_common = handle.read()
        def restore_common():
            with open(commondir, "w") as handle:
                handle.write(original_common)
        self.addCleanup(restore_common)
        with open(commondir, "w") as handle:
            handle.write("../..\n../..\n")
        request = self.custody_request(repo=self.worktree)
        response = self.observe(request, self.custody_owner(request),
                                in_process_transport())
        self.assertRefused(response, "git_pointer_invalid")

    def test_symlink_git_leaf_and_component_refused(self):
        # Symlinked worktree/.git leaf.
        link = os.path.join(self.base, "gitfile-link")
        os.symlink(self.wt_git_dir, link)
        worktree = os.path.join(self.base, "link-wt")
        os.makedirs(worktree)
        os.symlink(link, os.path.join(worktree, ".git"))
        request = self.custody_request_for(worktree, commit=self.commit)
        response = self.observe(request, self.custody_owner(request),
                                in_process_transport())
        self.assertRefused(response, "unsupported_git_link")
        # Symlinked git-dir component inside the boundary: lexical resolution
        # succeeds, the no-follow chain walk refuses.
        target_repo = build_repo(self.base, "sym-target")
        link_parent = os.path.join(self.base, "sym-link")
        os.symlink(target_repo, link_parent)
        sym_wt = os.path.join(self.base, "sym-wt")
        os.makedirs(sym_wt)
        with open(os.path.join(sym_wt, ".git"), "w") as handle:
            handle.write("gitdir: " + link_parent + "/.git\n")
        request = self.custody_request_for(sym_wt, commit=self.commit)
        response = self.observe(request, self.custody_owner(request),
                                in_process_transport())
        self.assertRefused(response, "filesystem_refused")
        # Symlinked commondir leaf under a real linked git_dir.
        commondir = os.path.join(self.wt_git_dir, "commondir")
        os.rename(commondir, commondir + ".orig")
        os.symlink(os.path.join(self.base, "elsewhere-common"), commondir)
        def restore():
            os.unlink(commondir)
            os.rename(commondir + ".orig", commondir)
        self.addCleanup(restore)
        request = self.custody_request(repo=self.worktree)
        response = self.observe(request, self.custody_owner(request),
                                in_process_transport())
        self.assertRefused(response, "custody_pointer_invalid")

    # -- mutation across resolution and capture ---------------------------
    def rewritten_pointer_capture(self, payload):
        """Swap worktree/.git the moment the first object store read happens:
        after resolution, during capture.  The graph held at resolution must
        refuse the run; no partial bytes are returned."""
        gitfile = os.path.join(self.worktree, ".git")
        with open(gitfile) as handle:
            original = handle.read()
        real_open = os.open
        state = {"count": 0}

        def opener(path, flags, dir_fd=None):
            if path == "objects" and dir_fd is not None:
                state["count"] += 1
                if state["count"] == 1:
                    os.unlink(gitfile)
                    with open(gitfile, "w") as handle:
                        handle.write(payload)
            return real_open(path, flags, dir_fd=dir_fd)

        def restore():
            if os.path.exists(gitfile):
                with open(gitfile, "w") as handle:
                    handle.write(original)
        self.addCleanup(restore)
        reader = cso.Reader(opener=opener)
        request = self.custody_request(repo=self.worktree)
        return request, self.custody_owner(request), lambda req: cso.canonical(
            cso.observe_remote(req, reader))

    def test_pointer_replaced_with_identical_bytes_refused(self):
        # Same bytes, new inode and timestamps: the identity half of the
        # retained graph still refuses the capture.
        with open(os.path.join(self.worktree, ".git")) as handle:
            original = handle.read()
        request, owner, transport = self.rewritten_pointer_capture(original)
        response = self.observe(request, owner, transport)
        self.assertEqual(response["status"], "UNAVAILABLE", response)
        self.assertEqual(response["reason"], "changed_during_read", response)
        self.assertEqual(response["files"], [])

    def test_pointer_changed_during_capture_refused(self):
        request, owner, transport = self.rewritten_pointer_capture(
            "gitdir: /nonexistent/elsewhere\n")
        response = self.observe(request, owner, transport)
        self.assertNotEqual(response["status"], "OBSERVED", response)
        self.assertIn(response["reason"],
                      ("changed_during_read", "git_pointer_mismatch"), response)
        self.assertEqual(response["files"], [])

    # -- delivered body, proof and publication -----------------------------
    def test_delivered_body_with_changed_resolved_paths_refused(self):
        request = self.custody_request(repo=self.worktree)
        def send(req):
            body = cso.observe_remote(req)
            self.assertEqual(body["status"], "OBSERVED", body)
            body["git_dir"] = body["common_dir"] + "/worktrees/forged"
            body["resolution"]["git_dir"] = body["git_dir"]
            return cso.canonical(body)
        response = self.observe(request, self.custody_owner(request), send)
        self.assertRefused(response, "custody_proof_invalid")

    def test_delivered_body_with_changed_proof_bytes_refused(self):
        request = self.custody_request(repo=self.worktree)
        def send(req):
            body = cso.observe_remote(req)
            self.assertEqual(body["status"], "OBSERVED", body)
            body["resolution"]["commondir"]["bytes_b64"] = base64.b64encode(
                b"../..\n../..").decode("ascii")
            return cso.canonical(body)
        response = self.observe(request, self.custody_owner(request), send)
        self.assertRefused(response, "custody_proof_invalid")

    def test_local_validation_rederives_proof_from_bytes_alone(self):
        sources = [{"path": path, "blob": self.wt_tree[path]["oid"],
                    "size": self.wt_tree[path]["size"]}
                   for path in sorted(self.wt_tree)]
        request = self.custody_request(repo=self.worktree, sources=sources)
        response = self.observe(request,
                                self.custody_owner(request),
                                in_process_transport())
        self.assertEqual(response["status"], "OBSERVED", response)
        cso.validate_resolution_proof(response["resolution"], response)
        # A different path inside the same boundary is not accepted for being
        # inside it: the returned bytes must re-derive the exact relationship.
        forged = copy.deepcopy(response)
        forged["git_dir"] = self.wt_common_dir + "/worktrees/other"
        forged["resolution"]["git_dir"] = forged["git_dir"]
        with self.assertRaisesRegex(cso.CurrentSourceError, "custody_proof_invalid"):
            cso.validate_resolution_proof(forged["resolution"], forged)
        # Broken backlink bytes.
        forged = copy.deepcopy(response)
        forged["resolution"]["gitdir_backlink"]["bytes_b64"] = base64.b64encode(
            (self.base + "/elsewhere/.git\n").encode()).decode("ascii")
        with self.assertRaisesRegex(cso.CurrentSourceError, "custody_proof_invalid"):
            cso.validate_resolution_proof(forged["resolution"], forged)
        # Unknown field inside the proof.
        forged = copy.deepcopy(response)
        forged["resolution"]["extra"] = "field"
        with self.assertRaisesRegex(cso.CurrentSourceError, "custody_proof_invalid"):
            cso.validate_resolution_proof(forged["resolution"], forged)
        # Triple responses still refuse the custody fields outright, and a
        # custody response missing its proof is refused.
        triple = self.observe(self.request(), self.owner(), in_process_transport())
        self.assertEqual(triple["status"], "OBSERVED", triple)
        with_extra = copy.deepcopy(triple)
        with_extra["resolution"] = response["resolution"]
        with_extra["receipt"]["response_sha256"] = cso.digest_of(
            {k: v for k, v in with_extra.items() if k != "receipt"})
        with self.assertRaisesRegex(cso.CurrentSourceError, "response_unknown_field"):
            cso.validate_response(with_extra)
        without_proof = copy.deepcopy(response)
        without_proof.pop("resolution")
        without_proof["receipt"]["response_sha256"] = cso.digest_of(
            {k: v for k, v in without_proof.items() if k != "receipt"})
        with self.assertRaisesRegex(cso.CurrentSourceError, "response_unknown_field"):
            cso.validate_response(without_proof)

    def test_publication_refuses_consistent_proof_for_other_boundary(self):
        # A fully self-consistent custody body for a DIFFERENT boundary still
        # cannot publish: the scope binds the declared boundary, and the
        # request digest (which binds custody) no longer matches.
        request = self.custody_request(repo=self.worktree)
        observed = self.observe(request, self.custody_owner(request),
                                in_process_transport())
        self.assertEqual(observed["status"], "OBSERVED", observed)
        # A real non-root strict ancestor of the fixtures -- never a hardcoded
        # /tmp, since the owned temp directories can live anywhere (macOS
        # /var/folders/..., /home/...).  Validated here so the forged body is
        # structurally valid and the refusal below is the scope binding's own.
        other_boundary = os.path.dirname(self.base)
        self.assertNotEqual(other_boundary, "/")
        self.assertTrue(self.base.startswith(other_boundary + "/"))
        self.assertNotEqual(other_boundary, request["custody"]["boundary"])
        forged = copy.deepcopy(observed)
        forged["custody"] = {"mode": cso.CUSTODY_MODE, "boundary": other_boundary}
        forged["resolution"]["boundary"] = other_boundary
        forged["receipt"]["response_sha256"] = cso.digest_of(
            {k: v for k, v in forged.items() if k != "receipt"})
        invocation = self.mint(request, self.custody_owner(request))
        with tempfile.TemporaryDirectory(prefix="custody-pub-") as dest:
            with self.assertRaisesRegex(cso.NativeRefused,
                                        "native_scope_caller_mismatch"):
                cso.publish_observation(forged, dest, invocation, reserve=TestChain)
            self.assertEqual(os.listdir(dest), [])
        # A foreign receiver is refused at the scope boundary as well.
        foreign = copy.deepcopy(observed)
        foreign["receiver"] = "receiver-2"
        foreign["receipt"]["receiver"] = "receiver-2"
        foreign["receipt"]["response_sha256"] = cso.digest_of(
            {k: v for k, v in foreign.items() if k != "receipt"})
        with tempfile.TemporaryDirectory(prefix="custody-pub-") as dest:
            with self.assertRaisesRegex(cso.NativeRefused,
                                        "native_scope_caller_mismatch"):
                cso.publish_observation(foreign, dest, invocation, reserve=TestChain)
            self.assertEqual(os.listdir(dest), [])

    def test_native_receipt_publishes_linked_resolution_and_refuses(self):
        from test_current_source_observation import TestChain, inert_request_loader
        sources = [{"path": path, "blob": self.wt_tree[path]["oid"],
                    "size": self.wt_tree[path]["size"]}
                   for path in sorted(self.wt_tree)]
        request = self.custody_request(repo=self.worktree, sources=sources)
        owner = self.custody_owner(request)
        with tempfile.TemporaryDirectory(prefix="custody-req-") as req_dir:
            request_path = os.path.join(req_dir, "request.json")
            with open(request_path, "wb") as handle:
                handle.write(cso.canonical(request))
            with tempfile.TemporaryDirectory(prefix="custody-dest-") as dest:
                summary = cso.native_current_source_receipt(
                    request_path, dest, lambda digest: owner,
                    transport=in_process_transport(), reserve=TestChain,
                    load_request=inert_request_loader)
                self.assertEqual(summary["state"], "PUBLISHED", summary)
                with open(summary["destination"], "rb") as handle:
                    stored = json.loads(handle.read().decode())
                cso.validate_response(stored)
                self.assertEqual(stored["custody"], request["custody"])
                self.assertEqual(stored["git_dir"], self.wt_git_dir)
                self.assertEqual(stored["common_dir"], self.wt_common_dir)
                self.assertEqual(stored["receipt"]["request_sha256"],
                                 cso.validate_request(request))
            # A duplicate destination refuses closed before any transport.
            with tempfile.TemporaryDirectory(prefix="custody-dest-") as dest:
                def reserve(_path):
                    raise cso.CurrentSourceError("duplicate_destination")
                with self.assertRaisesRegex(cso.CurrentSourceError,
                                            "duplicate_destination"):
                    cso.native_current_source_receipt(
                        request_path, dest, lambda digest: owner,
                        transport=self.refusing_transport(), reserve=reserve,
                        load_request=inert_request_loader)

    def test_response_caps_still_apply_to_custody_variant(self):
        request = self.custody_request(repo=self.worktree)
        original = cso.MAX_RESPONSE
        cso.MAX_RESPONSE = 200
        try:
            response = self.observe(request, self.custody_owner(request),
                                    in_process_transport())
        finally:
            cso.MAX_RESPONSE = original
        self.assertRefused(response, "response_limit")
        self.assertEqual(response["files"], [])


class CustodyGraphGuardTests(Host):
    """The held-descriptor graph guard for the custody variant: the full
    worktree/git_dir/common_dir chains and every no-follow pointer leaf are
    held open after resolution and re-verified against the discovery graph
    before inspect_custody, check_object_store or any object read, and again
    after capture.  Every trigger here is a real filesystem mutation observed
    through the Reader seams; OS identity values are never faked."""

    def linked_capture(self, opener=None):
        """Direct remote-half run over the real linked worktree with an
        injected Reader."""
        reader = cso.Reader() if opener is None else cso.Reader(opener=opener)
        request = self.custody_request(repo=self.worktree)
        return request, reader

    def swap_at_first_store_open(self, mutate, record=None):
        """An opener seam that mutates the graph the moment the first object
        store directory is opened -- after resolution and the guard's hold,
        during capture.  ``record`` collects every descriptor handed out."""
        real_open = os.open
        state = {"count": 0}

        def opener(path, flags, dir_fd=None):
            if path == "objects" and dir_fd is not None:
                state["count"] += 1
                if state["count"] == 1:
                    mutate()
            fd = real_open(path, flags, dir_fd=dir_fd)
            if record is not None:
                record.append(fd)
            return fd

        return opener

    def test_guard_verifies_before_inspect_store_and_objects(self):
        # Same bytes, new inode and timestamps, swapped the instant resolution
        # returns: the guard must refuse against the discovery graph before
        # inspect_custody runs and before a single object is read.
        gitfile = os.path.join(self.worktree, ".git")
        with open(gitfile) as handle:
            original = handle.read()
        real_resolve = cso.resolve_custody
        real_inspect = cso.inspect_custody
        seen = {"inspect": 0, "objects": 0}

        def resolve_then_replace(reader, req):
            result = real_resolve(reader, req)
            os.unlink(gitfile)
            with open(gitfile, "w") as handle:
                handle.write(original)
            return result

        def counting_inspect(reader, req):
            seen["inspect"] += 1
            return real_inspect(reader, req)

        def no_reads(*_args, **_kwargs):
            seen["objects"] += 1
            self.fail("an object read ran after the custody graph changed")

        def restore():
            with open(gitfile, "w") as handle:
                handle.write(original)
        self.addCleanup(restore)
        request, transport = self.linked_capture()
        with mock.patch.object(cso, "resolve_custody", resolve_then_replace), \
                mock.patch.object(cso, "inspect_custody", counting_inspect), \
                mock.patch.object(cso, "read_object", no_reads):
            body = cso.observe_remote(request, cso.Reader())
        self.assertEqual(body["status"], "UNAVAILABLE", body)
        self.assertEqual(body["reason"], "changed_during_read", body)
        self.assertEqual(body["files"], [])
        self.assertEqual(seen, {"inspect": 0, "objects": 0})

    def test_guard_verifies_again_immediately_before_objects(self):
        # Same-byte .git replacement during capture: the held leaf identity
        # refuses between inspect_custody and the first object read.
        gitfile = os.path.join(self.worktree, ".git")
        with open(gitfile) as handle:
            original = handle.read()

        def mutate():
            os.unlink(gitfile)
            with open(gitfile, "w") as handle:
                handle.write(original)

        def restore():
            with open(gitfile, "w") as handle:
                handle.write(original)
        self.addCleanup(restore)
        request, reader = self.linked_capture(
            self.swap_at_first_store_open(mutate))
        with mock.patch.object(cso, "read_object",
                               lambda *_a, **_k: self.fail(
                                   "object read ran on a changed graph")):
            body = cso.observe_remote(request, reader)
        self.assertEqual(body["status"], "UNAVAILABLE", body)
        self.assertEqual(body["reason"], "changed_during_read", body)
        self.assertEqual(body["files"], [])

    def test_guard_catches_reverted_pointer_ctime_during_capture(self):
        # commondir changed and reverted: the bytes match the discovery graph
        # again, but the identity (ctime) cannot, and the held leaf refuses.
        commondir = os.path.join(self.wt_git_dir, "commondir")
        with open(commondir) as handle:
            original = handle.read()

        def mutate():
            with open(commondir, "w") as handle:
                handle.write("/nonexistent/common\n")
            with open(commondir, "w") as handle:
                handle.write(original)

        def restore():
            with open(commondir, "w") as handle:
                handle.write(original)
        self.addCleanup(restore)
        request, reader = self.linked_capture(
            self.swap_at_first_store_open(mutate))
        with mock.patch.object(cso, "read_object",
                               lambda *_a, **_k: self.fail(
                                   "object read ran on a changed graph")):
            body = cso.observe_remote(request, reader)
        self.assertEqual(body["status"], "UNAVAILABLE", body)
        self.assertEqual(body["reason"], "changed_during_read", body)
        self.assertEqual(body["files"], [])

    def test_guard_catches_ancestor_rename_restore(self):
        # Rename an ancestor of the resolved git_dir/common_dir away and back
        # after discovery: no terminal identity moves, so only the held FULL
        # chain snapshot can refuse this before any object read.
        real_resolve = cso.resolve_custody

        def resolve_then_rename(reader, req):
            result = real_resolve(reader, req)
            os.rename(self.packed_repo, self.packed_repo + ".away")
            os.rename(self.packed_repo + ".away", self.packed_repo)
            return result

        request = self.custody_request(repo=self.worktree)
        with mock.patch.object(cso, "resolve_custody", resolve_then_rename), \
                mock.patch.object(cso, "read_object",
                                  lambda *_a, **_k: self.fail(
                                      "object read ran on a changed graph")):
            body = cso.observe_remote(request, cso.Reader())
        self.assertEqual(body["status"], "UNAVAILABLE", body)
        self.assertEqual(body["reason"], "changed_during_read", body)
        self.assertEqual(body["files"], [])

    def test_guard_refuses_leaf_made_symlink_after_discovery(self):
        # A linked leaf that becomes a symlink between resolution and the
        # hold is refused by the guard's own no-follow leaf discipline, still
        # before inspect_custody or any object read.
        commondir = os.path.join(self.wt_git_dir, "commondir")
        os.rename(commondir, commondir + ".orig")
        os.symlink(os.path.join(self.base, "elsewhere-common"), commondir)

        def restore():
            os.unlink(commondir)
            os.rename(commondir + ".orig", commondir)
        self.addCleanup(restore)
        real_resolve = cso.resolve_custody
        real_inspect = cso.inspect_custody
        seen = {"inspect": 0, "objects": 0}

        def resolve_then_link(reader, req):
            result = real_resolve(reader, req)
            os.unlink(commondir)
            os.symlink(os.path.join(self.base, "elsewhere-common"), commondir)
            return result

        def counting_inspect(reader, req):
            seen["inspect"] += 1
            return real_inspect(reader, req)

        request = self.custody_request(repo=self.worktree)
        with mock.patch.object(cso, "resolve_custody", resolve_then_link), \
                mock.patch.object(cso, "inspect_custody", counting_inspect), \
                mock.patch.object(cso, "read_object",
                                  lambda *_a, **_k: self.fail(
                                      "object read ran on a changed graph")):
            body = cso.observe_remote(request, cso.Reader())
        self.assertEqual(body["status"], "REFUSED", body)
        self.assertEqual(body["reason"], "custody_pointer_invalid", body)
        self.assertEqual(body["files"], [])
        self.assertEqual(seen, {"inspect": 0, "objects": 0})

    def test_guard_descriptors_close_on_success_and_on_error(self):
        # Every descriptor the Reader -- guard-held chains and leaves included
        # -- handed out is closed again, both for an observed capture and for
        # a refused one.  A loose linked worktree keeps the packed child out
        # of this leak check.
        loose_wt = os.path.join(self.base, "linked-loose-guard")
        run_git(self.repo, "worktree", "add", "-q", loose_wt, "-b", "wt-guard")
        def cleanup():
            shutil.rmtree(loose_wt, ignore_errors=True)
            run_git(self.repo, "worktree", "prune")
            run_git(self.repo, "branch", "-D", "wt-guard")
        self.addCleanup(cleanup)
        real_open = os.open
        opened = []

        def recorder(mutate=None, state=None):
            count = state if state is not None else {"n": 0}

            def opener(path, flags, dir_fd=None):
                if mutate is not None and path == "objects" and dir_fd is not None:
                    count["n"] += 1
                    if count["n"] == 1:
                        mutate()
                fd = real_open(path, flags, dir_fd=dir_fd)
                opened.append(fd)
                return fd

            return opener

        def assert_all_closed():
            self.assertTrue(opened)
            for fd in opened:
                with self.assertRaises(OSError):
                    os.fstat(fd)

        request = self.custody_request(repo=loose_wt)
        body = cso.observe_remote(request, cso.Reader(opener=recorder()))
        self.assertEqual(body["status"], "OBSERVED", body)
        assert_all_closed()
        # Error path: replace the linked .git with other bytes during capture
        # and confirm the held descriptors still all close.
        gitfile = os.path.join(loose_wt, ".git")
        with open(gitfile) as handle:
            original = handle.read()

        def mutate():
            with open(gitfile, "w") as handle:
                handle.write("gitdir: /nonexistent/guard\n")

        opened = []
        body = cso.observe_remote(request,
                                  cso.Reader(opener=recorder(mutate)))
        self.assertEqual(body["status"], "UNAVAILABLE", body)
        self.assertEqual(body["reason"], "changed_during_read", body)
        self.assertEqual(body["files"], [])
        assert_all_closed()
        with open(gitfile, "w") as handle:
            handle.write(original)

    def test_triple_mode_keeps_existing_pointer_state_behavior(self):
        # The explicit git_dir/common_dir triple keeps its own before/after
        # pointer behaviour and never constructs the guard.
        def no_guard(*_args, **_kwargs):
            self.fail("the explicit triple mode must not build a graph guard")
        with mock.patch.object(cso, "CustodyGraphGuard", no_guard):
            body = cso.observe_remote(self.request(), cso.Reader())
        self.assertEqual(body["status"], "OBSERVED", body)
        self.assertEqual([item["path"] for item in body["files"]],
                         sorted(FILES))

    def test_guard_ships_in_generated_reader(self):
        # The generated remote program must carry and execute the guard: the
        # linked custody path runs through it end to end.
        self.assertIn("class CustodyGraphGuard", cso.generated_reader_source())
        request = self.custody_request(repo=self.worktree)
        response = self.observe(request, self.custody_owner(request),
                                in_process_transport())
        self.assertEqual(response["status"], "OBSERVED", response)
        cso.validate_response(response)


class UnderscoreComponentTests(Host):
    """Leading-underscore relative source components (e.g. "__tests__") are
    admitted for requested source paths only; every neighbouring refusal and
    all existing custody/cap guards stay exactly as they were."""

    def test_leading_underscore_component_regex_boundary(self):
        # Admitted exactly according to the regex: underscore alone, underscore
        # prefixes and interior underscores, at the 128-character cap.
        for path in ("_", "__tests__", "_lead/mid_x/leaf_.ts",
                     "a" * 128, "_" * 128, "x_.-plus"):
            self.assertEqual(cso.validate_relative_path(path), path)
        # No blanket punctuation: dots, signs, spaces and empty components are
        # still refused, as is one character past the component cap.
        for path in (".", "..", ".lead", "a/.hidden", "-lead", "+lead",
                     "lead x", "", "a" * 129, "_" * 129):
            with self.assertRaises(cso.CurrentSourceError) as raised:
                cso.validate_relative_path(path)
            self.assertEqual(raised.exception.reason, "path_invalid")
        # Declared custody roots keep their own unchanged rule: a leading
        # underscore component is still refused there.
        with self.assertRaises(cso.CurrentSourceError) as raised:
            cso.validate_absolute_custody("/fixture-root/_custody")
        self.assertEqual(raised.exception.reason, "custody_path_invalid")

    def test_all_eight_underscore_paths_validate_and_observe(self):
        # Exactly MAX_SOURCES entries: the all-eight request fits the existing
        # cap and validates, and one more entry is refused without a read.
        request = self.eight_request()
        self.assertEqual(len(request["sources"]), cso.MAX_SOURCES)
        digest = cso.validate_request(request)
        self.assertEqual(digest, cso.digest_of(request))
        crowded = self.eight_request()
        crowded["sources"] = (crowded["sources"]
                              + [{"path": "terminal/lib/one.ts"}])
        with self.assertRaises(cso.CurrentSourceError) as raised:
            cso.validate_request(crowded)
        self.assertEqual(raised.exception.reason, "entry_count_limit")
        # The real generated reader delivers all eight blobs, bound to the
        # request, the exact bytes and the actual Git OIDs and tree.
        fixture = self.eight_fixture()
        root_tree = run_git(fixture["repo"], "rev-parse",
                            fixture["commit"] + "^{tree}")
        response = self.observe(request, self.owner_bound(request),
                                in_process_transport())
        self.assertEightPathsBound(request, response, root_tree)
        cso.validate_response(response)

    def test_all_eight_paths_through_linked_custody_variant(self):
        # The additive resolution variant over a real linked worktree of the
        # eight-path store: same generated reader, resolved triple plus the
        # bounded graph proof, published receipt still binds the request.
        request = self.eight_request(linked=True)
        fixture = self.eight_fixture()
        root_tree = run_git(fixture["repo"], "rev-parse",
                            fixture["commit"] + "^{tree}")
        response = self.observe(request, self.owner_bound(request),
                                in_process_transport())
        self.assertEightPathsBound(request, response, root_tree)
        cso.validate_response(response)
        self.assertEqual(response["custody"], request["custody"])
        with open(os.path.join(fixture["linked"], ".git")) as handle:
            git_dir = handle.read().split("gitdir: ", 1)[1].strip()
        self.assertEqual(response["git_dir"], git_dir)
        self.assertEqual(response["common_dir"],
                         os.path.join(fixture["repo"], ".git"))
        self.assertEqual(response["resolution"]["worktree"], fixture["linked"])

    def test_underscore_boundary_neighbors_stay_refused(self):
        # Every neighbouring path shape the fix must not admit, refused with
        # the retained reason before admission and before any read.
        neighbors = ("../escape.ts", "./here.ts", ".hidden/leaf.ts",
                     "terminal/.hidden/leaf.ts", "/abs/terminal/lib/x.ts",
                     "terminal//x.ts", "terminal/lib/__tests__/",
                     "-lead/terminal.ts", "+lead/terminal.ts",
                     "terminal/lib/lead _.ts", "n" * 129 + ".ts",
                     "terminal/lib/portfolio.ts/")
        for path in neighbors:
            request = self.request(sources=[{"path": path}])
            with self.assertRaises(cso.CurrentSourceError) as raised:
                cso.validate_request(request)
            self.assertEqual(raised.exception.reason, "path_invalid", path)
            def no_transport(_request, path=path):
                self.fail("a refused %r path reached transport" % path)
            response = cso.observe_current_source(request, None, no_transport)
            self.assertRefused(response, "path_invalid", state="NOT_SEEKED")
            self.assertEqual(response["files"], [])

    def test_unknown_fields_refused_for_underscore_request(self):
        request = self.eight_request()
        entry_bad = self.eight_request()
        entry_bad["sources"] = [dict(entry, extra=1)
                                for entry in entry_bad["sources"]]
        with self.assertRaises(cso.CurrentSourceError) as raised:
            cso.validate_request(entry_bad)
        self.assertEqual(raised.exception.reason, "entry_unknown_field")
        request_bad = self.eight_request()
        request_bad["unexpected"] = 1
        with self.assertRaises(cso.CurrentSourceError) as raised:
            cso.validate_request(request_bad)
        self.assertEqual(raised.exception.reason, "request_unknown_field")

    def test_refused_underscore_request_publishes_no_destination(self):
        # Native rejection happens before the destination is even reserved:
        # no owner, no transport, no reservation, no bytes.
        refused = self.eight_request()
        refused["sources"] = [{"path": "terminal/lib/__tests__/"}]
        reserved = []
        def reserve(destination):
            reserved.append(destination)
            return TestChain(destination)
        with tempfile.TemporaryDirectory(prefix="cso-refused-") as req_dir:
            request_path = os.path.join(req_dir, "request.json")
            with open(request_path, "wb") as handle:
                handle.write(cso.canonical(refused))
            with tempfile.TemporaryDirectory(prefix="cso-dest-") as dest:
                def factory(_digest):
                    self.fail("an invalid request minted an invocation")
                with self.assertRaises(cso.CurrentSourceError) as raised:
                    cso.native_current_source_receipt(
                        request_path, dest, factory, transport=None,
                        reserve=reserve, load_request=inert_request_loader)
                self.assertEqual(raised.exception.reason, "path_invalid")
                self.assertEqual(reserved, [])
                self.assertEqual(os.listdir(dest), [])

    def test_native_receipt_publishes_all_eight_blobs_inert(self):
        # The inert composition: owned request file -> minted invocation ->
        # generated reader -> exclusive receipt binding the original request
        # and all eight blobs.
        request = self.eight_request()
        fixture = self.eight_fixture()
        root_tree = run_git(fixture["repo"], "rev-parse",
                            fixture["commit"] + "^{tree}")
        owner = self.owner_bound(request)
        with tempfile.TemporaryDirectory(prefix="cso-req-") as req_dir:
            request_path = os.path.join(req_dir, "request.json")
            with open(request_path, "wb") as handle:
                handle.write(cso.canonical(request))
            with tempfile.TemporaryDirectory(prefix="cso-dest-") as dest:
                summary = cso.native_current_source_receipt(
                    request_path, dest, lambda _digest: owner,
                    transport=in_process_transport(), reserve=TestChain,
                    load_request=inert_request_loader)
                self.assertEqual(summary["state"], "PUBLISHED", summary)
                self.assertEqual(os.listdir(dest),
                                 [os.path.basename(summary["destination"])])
                with open(summary["destination"], "rb") as handle:
                    stored = json.loads(handle.read().decode())
        cso.validate_response(stored)
        self.assertEightPathsBound(request, stored, root_tree)
        receipt = stored["receipt"]
        self.assertEqual(receipt["request_sha256"], cso.validate_request(request))
        self.assertEqual(receipt["receiver"], request["receiver"])
        self.assertEqual(receipt["root"], request["root"])
        self.assertEqual(receipt["commit"], request["commit"])
        self.assertEqual(receipt["no_claims"], list(cso.NO_CLAIMS))


if __name__ == "__main__":
    unittest.main(verbosity=2)
