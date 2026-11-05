"""Real-Git negative and positive checks for ``workspace_project_git_publisher``.

Every test drives the actual ``git`` binary against a temporary bare remote and a
private clone.  There is no network access, no live GitHub call and no installed
service: the pull-request seam is an inert in-test object whose PR metadata lives
in the test object only, and the proposal compiler is an explicit, fully authored
fixture that the parent joins to the actual canonical compiler later.

These are source-only unit tests.  A green run here is not a live publication
and is not proof of a live publication.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from types import SimpleNamespace

import pytest

from control_plane import workspace_project_git_publisher as pub

# --------------------------------------------------------------------------- #
# Closed expectations (declared independently of the module under test)
# --------------------------------------------------------------------------- #

REPOSITORY = "mastermindx-market-intelligence/macro"
DEFAULT_BRANCH = "main"
WORK_REF = "WS:DEMO"
CANONICAL_PATH = "agentos/workstreams/WS-DEMO.md"
CONTENT = (
    "# WS-DEMO\n\n"
    "Authored workspace project document for the demo workstream.\n\n"
    "## Outcome\n\n- single canonical source file\n"
)
REQUEST_ID = "mmos-project-create-" + "1" * 40
PUBLISHER_IDENTITY = "test-publisher-identity:" + hashlib.sha256(
    b"unit-fixture-publisher"
).hexdigest()

RESULT_KEYS = {
    "schema",
    "state",
    "request_sha256",
    "work_ref",
    "branch",
    "source",
    "proposal",
    "reason",
    "retryable",
}
SOURCE_KEYS = {"repository", "commit", "path", "content_sha256", "request_sha256"}
RECEIPT_KEYS = {"number", "url", "head_commit", "head_branch"}

def make_publisher(*args, **kwargs):
    return pub.FixedProjectGitPublisher(*args, principal_scope=lambda principal: hashlib.sha256(principal.subject.encode()).hexdigest(), **kwargs)


MODULE_GLOBALS_AT_IMPORT = frozenset(vars(pub).keys())


# --------------------------------------------------------------------------- #
# Git helpers (real binary, no shell)
# --------------------------------------------------------------------------- #


def git(cwd, *args, stdin=None):
    if isinstance(stdin, str):
        stdin = stdin.encode("utf-8")
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={k: v for k, v in os.environ.items() if k not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR"}},
    )
    if proc.returncode != 0:
        raise AssertionError(
            "git %s failed (%d): %s"
            % (" ".join(args), proc.returncode, proc.stderr.decode()[-800:])
        )
    return proc.stdout.decode("utf-8", "surrogateescape")


def refs(repo):
    return git(repo, "for-each-ref", "--format=%(refname) %(objectname)")


def objects(repo):
    return git(repo, "count-objects", "-v")


def rev_parse(repo, revision):
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", revision],
        cwd=str(repo),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={k: v for k, v in os.environ.items() if k not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR"}},
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.decode().strip()


def snapshot(repo):
    return {"refs": refs(repo), "objects": objects(repo)}


def assert_unchanged(before, repo):
    assert before == snapshot(repo), "unexpected Git writes in %s" % repo


def stable_branch(request=None, principal=AUTHORIZED_PRINCIPAL if "AUTHORIZED_PRINCIPAL" in globals() else None):
    principal = principal or AUTHORIZED_PRINCIPAL
    request = request or make_request()
    identity = {"principal_scope": hashlib.sha256(principal.subject.encode()).hexdigest(), "request_id": request["request_id"], "work_ref": request["work_ref"]}
    return "mmos/new-project-" + hashlib.sha256(canonical_request_bytes(identity)).hexdigest()


def canonical_request_bytes(request):
    return json.dumps(request, sort_keys=True, separators=(",", ":")).encode("utf-8")


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def isolated_git_env(tmp_path, monkeypatch):
    """Isolate git identity/config so tests never touch host state."""
    config = tmp_path / "gitconfig"
    config.write_text(
        "[init]\n\tdefaultBranch = main\n"
        "[commit]\n\tgpgsign = false\n"
        "[tag]\n\tgpgsign = false\n"
        "[core]\n\tautocrlf = false\n"
        "[advice]\n\t detachedHead = false\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "MMOS Publisher Fixture")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "publisher-fixture@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "MMOS Publisher Fixture")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "publisher-fixture@example.invalid")


@pytest.fixture
def env(tmp_path):
    """Temporary bare origin plus a private clone of it."""
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", str(origin))
    seed = tmp_path / "seed"
    git(tmp_path, "clone", str(origin), str(seed))
    (seed / "README.md").write_text("seed\n", encoding="utf-8")
    git(seed, "add", "README.md")
    git(seed, "commit", "-m", "seed")
    git(seed, "push", "-u", "origin", "main")
    clone = tmp_path / "clone"
    git(tmp_path, "clone", str(origin), str(clone))
    return SimpleNamespace(tmp_path=tmp_path, origin=origin, seed=seed, clone=clone)


class AuthoredProposalCompiler:
    """Explicit, fully authored canonical-envelope fixture.

    Emits a valid closed ``agentos.project_proposal.v1`` envelope with complete
    authored metadata and no inferred owner.  The parent joins the actual
    canonical compiler later; this fixture only stands in for its output shape.
    """

    def __init__(self, expected_commit, work_ref=WORK_REF, content=CONTENT, path=None):
        self.expected_commit = expected_commit
        self.work_ref = work_ref
        self.content = content
        self.path = path or ("agentos/workstreams/WS-%s.md" % work_ref[3:])
        self.requests_seen = []

    def __call__(self, request):
        self.requests_seen.append(request)
        request_sha256 = hashlib.sha256(canonical_request_bytes(request)).hexdigest()
        content_bytes = self.content.encode("utf-8")
        return {
            "schema": "agentos.project_proposal.v1",
            "state": "DRAFT_ONLY",
            "request_id": request["request_id"],
            "request_sha256": request_sha256,
            "expected_commit": self.expected_commit,
            "work_ref": self.work_ref,
            "path": self.path,
            "content_utf8": self.content,
            "content_sha256": hashlib.sha256(content_bytes).hexdigest(),
        }


class Principal:
    def __init__(self, subject):
        self.subject = subject


AUTHORIZED_PRINCIPAL = Principal("mmos-workspace-project-owner@fixture")


def authorize(principal):
    return principal is AUTHORIZED_PRINCIPAL


def permission_stamp(principal):
    return hashlib.sha256(
        ("permission-stamp:" + principal.subject).encode("utf-8")
    ).hexdigest()


def qualify_publisher(binding):
    """Inert synthetic qualifier: real credential identity qualification is
    mounted separately and reviewed before production."""
    return binding.repository == REPOSITORY


class InertPullRequestOwner:
    """Inert PR seam.  Real PR metadata is stored in this TEST object only."""

    def __init__(self, origin, repository=REPOSITORY):
        self.origin = str(origin)
        self.repository = repository
        self.pull_requests = {}
        self.counter = 400
        self.find_calls = 0
        self.create_calls = 0
        self.find_error = None
        self.create_error = None

    def _head_commit(self, branch):
        commit = rev_parse(self.origin, "refs/heads/" + branch)
        assert commit is not None, "fixture PR needs the branch on the remote"
        return commit

    def find(self, binding, branch, request_sha256):
        self.find_calls += 1
        if self.find_error is not None:
            raise self.find_error
        receipt = self.pull_requests.get(branch)
        return dict(receipt) if receipt else None

    def create(self, binding, branch, expected_commit, request_sha256):
        self.create_calls += 1
        if self.create_error is not None:
            raise self.create_error
        self.counter += 1
        receipt = {
            "number": self.counter,
            "url": "https://github.com/%s/pull/%d" % (self.repository, self.counter),
            "head_commit": self._head_commit(branch),
            "head_branch": branch,
        }
        self.pull_requests[branch] = dict(receipt)
        return dict(receipt)


def build_publisher(
    env, expected_commit, compiler=None, pr_owner=None,
    expected_origin=None, default_branch=None,
):
    binding = pub.PublisherBinding(
        worktree=str(env.clone),
        expected_origin=expected_origin or str(env.origin),
        default_branch=default_branch or DEFAULT_BRANCH,
        publisher_identity=PUBLISHER_IDENTITY,
    )
    compiler = compiler or AuthoredProposalCompiler(expected_commit)
    pr_owner = pr_owner or InertPullRequestOwner(env.origin)
    publisher = make_publisher(
        binding,
        compiler,
        authorize,
        permission_stamp,
        qualify_publisher,
        pr_owner,
    )
    return SimpleNamespace(
        publisher=publisher,
        binding=binding,
        compiler=compiler,
        pr_owner=pr_owner,
    )


def make_request(request_id=REQUEST_ID, work_ref=WORK_REF):
    return {
        "request_id": request_id,
        "work_ref": work_ref,
        "title": "Demo workspace project",
        "summary": "Authored demo workspace project for the fixture workstream.",
    }


def expected_commit_of(env):
    return rev_parse(env.clone, "refs/heads/" + DEFAULT_BRANCH)


def assert_closed_result(result):
    assert set(result.keys()) == RESULT_KEYS
    assert result["schema"] == "mastermind.workspace_project_publication.v1"
    assert result["state"] in pub.PUBLICATION_STATES
    assert result["retryable"] is False


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #


def test_publish_creates_proposal_branch_and_single_pr(env):
    handle = build_publisher(env, expected_commit_of(env))
    before_clone = snapshot(env.clone)
    before_origin = snapshot(env.origin)
    default_before = rev_parse(env.clone, "refs/heads/" + DEFAULT_BRANCH)

    result = handle.publisher.publish(make_request(), AUTHORIZED_PRINCIPAL)

    assert_closed_result(result)
    request_sha256 = hashlib.sha256(canonical_request_bytes(make_request())).hexdigest()
    assert result["state"] == "PROPOSAL_PUBLISHED"
    assert result["request_sha256"] == request_sha256
    assert result["work_ref"] == WORK_REF
    branch = stable_branch()
    assert result["branch"] == branch
    assert result["source"] is None
    assert result["reason"] is None

    receipt = result["proposal"]
    assert set(receipt.keys()) == RECEIPT_KEYS
    remote_commit = rev_parse(env.origin, "refs/heads/" + branch)
    assert remote_commit is not None, "proposal branch must be on the verified origin"
    assert receipt["head_commit"] == remote_commit
    assert receipt["head_branch"] == branch
    assert receipt["url"] == "https://github.com/%s/pull/%d" % (
        REPOSITORY,
        receipt["number"],
    )
    assert isinstance(receipt["number"], int) and receipt["number"] > 0

    # Canonical file exists only on the exact single-parent proposal commit.
    parents = git(env.clone, "rev-list", "--parents", "-n", "1", remote_commit).split()
    assert parents == [remote_commit, expected_commit_of(env)]
    delta = [
        line
        for line in git(env.clone, "diff-tree", "-r", "--no-commit-id", "--name-only", remote_commit).splitlines()
        if line
    ]
    assert delta == [CANONICAL_PATH]
    blob = git(env.clone, "cat-file", "blob", "%s:%s" % (remote_commit, CANONICAL_PATH))
    assert blob == CONTENT
    assert hashlib.sha256(blob.encode("utf-8")).hexdigest() == hashlib.sha256(
        CONTENT.encode("utf-8")
    ).hexdigest()

    # Default branch untouched; caller refs untouched; exactly one PR.
    assert rev_parse(env.clone, "refs/heads/" + DEFAULT_BRANCH) == default_before
    assert rev_parse(env.origin, "refs/heads/" + DEFAULT_BRANCH) == default_before
    assert CANONICAL_PATH not in git(env.clone, "ls-tree", "-r", "--name-only", default_before)
    assert len(handle.pr_owner.pull_requests) == 1
    assert handle.pr_owner.create_calls == 1
    assert handle.compiler.requests_seen == [make_request()]
    # No runtime ledger in the module: globals are exactly the import-time set.
    assert frozenset(vars(pub).keys()) == MODULE_GLOBALS_AT_IMPORT


def test_second_publish_of_same_request_reconciles_without_new_branch_or_pr(env):
    handle = build_publisher(env, expected_commit_of(env))
    first = handle.publisher.publish(make_request(), AUTHORIZED_PRINCIPAL)
    assert first["state"] == "PROPOSAL_PUBLISHED"
    branch = first["branch"]
    branch_commit = rev_parse(env.origin, "refs/heads/" + branch)
    receipt_before = dict(handle.pr_owner.pull_requests[branch])

    second = handle.publisher.publish(make_request(), AUTHORIZED_PRINCIPAL)

    assert_closed_result(second)
    assert second["state"] == "PROPOSAL_PUBLISHED"
    assert second["branch"] == branch
    assert second["proposal"]["number"] == receipt_before["number"]
    assert rev_parse(env.origin, "refs/heads/" + branch) == branch_commit
    assert handle.pr_owner.create_calls == 1, "no second PR"
    assert len(handle.pr_owner.pull_requests) == 1, "no second PR record"


def test_canonical_merged_readback_returns_project_created(env):
    handle = build_publisher(env, expected_commit_of(env))
    published = handle.publisher.publish(make_request(), AUTHORIZED_PRINCIPAL)
    assert published["state"] == "PROPOSAL_PUBLISHED"
    branch = published["branch"]

    # Someone else performs the normal protected merge (never this publisher).
    integrator = env.tmp_path / "integrator"
    git(env.tmp_path, "clone", str(env.origin), str(integrator))
    git(integrator, "fetch", "origin", branch)
    git(integrator, "checkout", "-q", DEFAULT_BRANCH)
    git(integrator, "merge", "--no-ff", "--no-edit", "FETCH_HEAD")
    git(integrator, "push", "origin", DEFAULT_BRANCH)
    merged_commit = rev_parse(env.origin, "refs/heads/" + DEFAULT_BRANCH)
    # The caller's own clone syncs its default branch after the protected merge.
    git(env.clone, "fetch", "origin", DEFAULT_BRANCH)
    git(env.clone, "merge", "--ff-only", "FETCH_HEAD")
    assert rev_parse(env.clone, "refs/heads/" + DEFAULT_BRANCH) == merged_commit

    fresh = build_publisher(env, merged_commit)
    result = fresh.publisher.publish(make_request(), AUTHORIZED_PRINCIPAL)

    assert_closed_result(result)
    assert result["state"] == "PROJECT_CREATED"
    assert result["branch"] == branch
    source = result["source"]
    assert set(source.keys()) == SOURCE_KEYS
    assert source["repository"] == "macro"
    assert source["commit"] == merged_commit
    assert source["path"] == CANONICAL_PATH
    assert source["request_sha256"] == result["request_sha256"]
    assert source["content_sha256"] == hashlib.sha256(CONTENT.encode("utf-8")).hexdigest()
    # The read-back default commit actually carries the authored bytes.
    assert git(integrator, "cat-file", "blob", "%s:%s" % (merged_commit, CANONICAL_PATH)) == CONTENT


# --------------------------------------------------------------------------- #
# Effect-unknown and reconciliation
# --------------------------------------------------------------------------- #


def test_unknown_pr_response_is_effect_unknown_then_readonly_reconcile(env):
    handle = build_publisher(env, expected_commit_of(env))
    handle.pr_owner.create_error = pub.PrOwnerUnknownOutcome("fixture: gh 5xx")

    result = handle.publisher.publish(make_request(), AUTHORIZED_PRINCIPAL)

    assert_closed_result(result)
    assert result["state"] == "EFFECT_UNKNOWN"
    assert result["reason"] == "PR_CREATION_UNKNOWN"
    assert result["retryable"] is False
    branch = result["branch"]
    assert rev_parse(env.origin, "refs/heads/" + branch) is not None
    assert handle.pr_owner.pull_requests == {}
    before_origin = snapshot(env.origin)

    # The write actually landed upstream: the PR exists after all.  Reconcile
    # must discover it READ-ONLY (no push, no create, no new Git writes).
    head = rev_parse(env.origin, "refs/heads/" + branch)
    handle.pr_owner.pull_requests[branch] = {
        "number": 401,
        "url": "https://github.com/%s/pull/401" % REPOSITORY,
        "head_commit": head,
        "head_branch": branch,
    }
    create_calls = handle.pr_owner.create_calls
    find_calls = handle.pr_owner.find_calls
    before_clone = snapshot(env.clone)

    reconciled = handle.publisher.reconcile(make_request(), AUTHORIZED_PRINCIPAL)

    assert_closed_result(reconciled)
    assert reconciled["state"] == "PROPOSAL_PUBLISHED"
    assert reconciled["branch"] == branch
    assert reconciled["proposal"]["number"] == 401
    assert handle.pr_owner.create_calls == create_calls, "reconcile never creates"
    assert handle.pr_owner.find_calls >= find_calls + 1
    assert_unchanged(before_origin, env.origin)
    assert_unchanged(before_clone, env.clone)


def test_reconcile_before_any_publication_is_read_only(env):
    handle = build_publisher(env, expected_commit_of(env))
    before_clone = snapshot(env.clone)
    before_origin = snapshot(env.origin)

    result = handle.publisher.reconcile(make_request(), AUTHORIZED_PRINCIPAL)

    assert_closed_result(result)
    assert result["state"] == "EFFECT_UNKNOWN"
    assert result["reason"] == "NO_EXISTING_PUBLICATION"
    assert result["proposal"] is None and result["source"] is None
    assert handle.pr_owner.create_calls == 0
    assert handle.pr_owner.find_calls == 1
    assert_unchanged(before_clone, env.clone)
    assert_unchanged(before_origin, env.origin)


# --------------------------------------------------------------------------- #
# Revocation windows
# --------------------------------------------------------------------------- #


def test_revocation_before_effect_writes_nothing(env):
    class RevokedAuthorizer:
        def __call__(self, principal):
            return False

    handle = build_publisher(env, expected_commit_of(env))
    publisher = make_publisher(
        handle.binding,
        handle.compiler,
        RevokedAuthorizer(),
        permission_stamp,
        qualify_publisher,
        handle.pr_owner,
    )
    before_clone = snapshot(env.clone)
    before_origin = snapshot(env.origin)

    result = publisher.publish(make_request(), AUTHORIZED_PRINCIPAL)

    assert_closed_result(result)
    assert result["state"] == "NOT_DISPATCHED"
    assert result["reason"] == "UNAUTHORIZED"
    assert_unchanged(before_clone, env.clone)
    assert_unchanged(before_origin, env.origin)
    assert handle.pr_owner.create_calls == 0


def test_revocation_after_write_is_effect_unknown(env):
    """Authorization is revoked once the branch has reached the origin, so the
    pre-PR-create guard fails after a real write."""
    handle = build_publisher(env, expected_commit_of(env))

    def authorizer(principal):
        branch = stable_branch()
        if authorize(principal) is not True:
            return False
        return rev_parse(env.origin, "refs/heads/" + branch) is None

    publisher = make_publisher(
        handle.binding,
        handle.compiler,
        authorizer,
        permission_stamp,
        qualify_publisher,
        handle.pr_owner,
    )
    before_origin = snapshot(env.origin)

    result = publisher.publish(make_request(), AUTHORIZED_PRINCIPAL)

    assert_closed_result(result)
    assert result["state"] == "EFFECT_UNKNOWN"
    assert result["reason"] == "AUTHORIZATION_REVOKED"
    branch = result["branch"]
    assert rev_parse(env.origin, "refs/heads/" + branch) is not None, "push already landed"
    assert handle.pr_owner.create_calls == 0, "no PR after revocation"


# --------------------------------------------------------------------------- #
# Closed refusals
# --------------------------------------------------------------------------- #


def test_foreign_expected_origin_is_rejected(env, tmp_path):
    foreign = tmp_path / "foreign.git"
    git(tmp_path, "init", "--bare", str(foreign))
    handle = build_publisher(
        env, expected_commit_of(env), expected_origin=str(foreign)
    )
    before_clone = snapshot(env.clone)

    result = handle.publisher.publish(make_request(), AUTHORIZED_PRINCIPAL)

    assert result["state"] == "NOT_DISPATCHED"
    assert result["reason"] == "ORIGIN_MISMATCH"
    assert_unchanged(before_clone, env.clone)


def test_stale_expected_commit_is_rejected(env):
    stale_parent = expected_commit_of(env)
    (env.clone / "unrelated-later.txt").write_text("later\n", encoding="utf-8")
    git(env.clone, "add", "unrelated-later.txt")
    git(env.clone, "commit", "-m", "advance main locally")
    git(env.clone, "push", "origin", "main")
    handle = build_publisher(env, stale_parent)
    before_clone = snapshot(env.clone)
    before_origin = snapshot(env.origin)

    result = handle.publisher.publish(make_request(), AUTHORIZED_PRINCIPAL)

    assert_closed_result(result)
    assert result["state"] == "NOT_DISPATCHED"
    assert result["reason"] == "STALE_EXPECTED_COMMIT"
    assert_unchanged(before_clone, env.clone)
    assert_unchanged(before_origin, env.origin)


def test_path_outside_derived_canonical_form_is_rejected(env):
    broken = AuthoredProposalCompiler(
        expected_commit_of(env), path="agentos/workstreams/../../evil.md"
    )
    handle = build_publisher(env, expected_commit_of(env), compiler=broken)
    before_clone = snapshot(env.clone)
    before_origin = snapshot(env.origin)

    result = handle.publisher.publish(make_request(), AUTHORIZED_PRINCIPAL)

    assert_closed_result(result)
    assert result["state"] == "NOT_DISPATCHED"
    assert result["reason"] == "PROPOSAL_INVALID"
    assert result["source"] is None and result["proposal"] is None
    assert_unchanged(before_clone, env.clone)
    assert_unchanged(before_origin, env.origin)
    assert not (env.clone / "evil.md").exists()


def test_differing_existing_canonical_file_conflicts(env):
    existing = env.clone / CANONICAL_PATH
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("# WS-DEMO\n\nDifferent authored content.\n", encoding="utf-8")
    git(env.clone, "add", CANONICAL_PATH)
    git(env.clone, "commit", "-m", "pre-existing canonical file with other content")
    git(env.clone, "push", "origin", DEFAULT_BRANCH)
    handle = build_publisher(env, expected_commit_of(env))
    before_clone = snapshot(env.clone)
    before_origin = snapshot(env.origin)

    result = handle.publisher.publish(make_request(), AUTHORIZED_PRINCIPAL)

    assert_closed_result(result)
    assert result["state"] == "CONFLICT"
    assert result["reason"] == "DEFAULT_BYTES_CONFLICT"
    assert_unchanged(before_clone, env.clone)
    assert_unchanged(before_origin, env.origin)


def test_existing_local_branch_collision_is_rejected_not_overwritten(env):
    request_sha256 = hashlib.sha256(canonical_request_bytes(make_request())).hexdigest()
    branch = stable_branch()
    collision_base = expected_commit_of(env)
    # An unrelated single-parent commit on the same base but a different file.
    blob = git(env.clone, "hash-object", "-w", "--stdin", stdin=b"unrelated collision\n").strip()
    tree = git(env.clone, "mktree", stdin="100644 blob %s\tcollision.txt\n" % blob).strip()
    collision_commit = git(env.clone, "commit-tree", tree, "-p", collision_base, "-m", "unrelated").strip()
    git(env.clone, "update-ref", "refs/heads/" + branch, collision_commit, "0" * 40)
    handle = build_publisher(env, collision_base)
    before_origin = snapshot(env.origin)

    result = handle.publisher.publish(make_request(), AUTHORIZED_PRINCIPAL)

    assert_closed_result(result)
    assert result["state"] == "CONFLICT"
    assert result["reason"] == "REF_COLLISION"
    assert rev_parse(env.clone, "refs/heads/" + branch) == collision_commit
    assert rev_parse(env.origin, "refs/heads/" + branch) is None
    assert_unchanged(before_origin, env.origin)


# --------------------------------------------------------------------------- #
# Caller state preservation
# --------------------------------------------------------------------------- #


def test_caller_head_index_and_dirty_files_are_preserved(env):
    handle = build_publisher(env, expected_commit_of(env))
    (env.clone / "notes").mkdir()
    (env.clone / "notes" / "scratch.txt").write_text("dirty\n", encoding="utf-8")
    (env.clone / "README.md").write_text("seed\nedited locally\n", encoding="utf-8")
    (env.clone / "staged.txt").write_text("staged\n", encoding="utf-8")
    git(env.clone, "add", "staged.txt")
    git(env.clone, "branch", "caller-work")
    head_before = rev_parse(env.clone, "HEAD")
    status_before = git(env.clone, "status", "--porcelain")
    staged_before = git(env.clone, "diff", "--cached", "--name-only")

    result = handle.publisher.publish(make_request(), AUTHORIZED_PRINCIPAL)

    assert_closed_result(result)
    assert result["state"] == "PROPOSAL_PUBLISHED"
    assert rev_parse(env.clone, "HEAD") == head_before
    assert git(env.clone, "status", "--porcelain") == status_before
    assert git(env.clone, "diff", "--cached", "--name-only") == staged_before
    assert staged_before.split() == ["staged.txt"]
    assert rev_parse(env.clone, "refs/heads/caller-work") == head_before
    assert (env.clone / "notes" / "scratch.txt").read_text(encoding="utf-8") == "dirty\n"
    assert not (env.clone / CANONICAL_PATH).exists(), "never writes the worktree file"


def test_pr_creation_refused_leaves_prepared_branch(env):
    handle = build_publisher(env, expected_commit_of(env))
    handle.pr_owner.create_error = pub.PrOwnerRefused("fixture: PR closed refusal")

    result = handle.publisher.publish(make_request(), AUTHORIZED_PRINCIPAL)

    assert_closed_result(result)
    assert result["state"] == "PREPARED"
    assert result["reason"] == "PR_CREATION_REFUSED"
    assert result["proposal"] is None
    assert result["source"] is None
    assert rev_parse(env.origin, "refs/heads/" + result["branch"]) is not None


def test_public_result_exposes_no_sensitive_material(env):
    handle = build_publisher(env, expected_commit_of(env))

    result = handle.publisher.publish(make_request(), AUTHORIZED_PRINCIPAL)

    encoded = json.dumps(result)
    assert CONTENT not in encoded
    assert str(env.clone) not in encoded
    assert PUBLISHER_IDENTITY not in encoded
    assert "token" not in encoded.lower()
    assert "goal" not in encoded
    assert set(result.keys()) == RESULT_KEYS


# --------------------------------------------------------------------------- #
# Seam construction refusals
# --------------------------------------------------------------------------- #


def test_missing_or_labelled_seams_are_refused_at_construction(env):
    binding = pub.PublisherBinding(
        worktree=str(env.clone),
        expected_origin=str(env.origin),
        default_branch=DEFAULT_BRANCH,
        publisher_identity=PUBLISHER_IDENTITY,
    )
    good = (
        AuthoredProposalCompiler(expected_commit_of(env)),
        authorize,
        permission_stamp,
        qualify_publisher,
        InertPullRequestOwner(env.origin),
    )
    with pytest.raises(TypeError):
        make_publisher(
            binding, good[0], good[1], good[2], good[3], None
        )
    with pytest.raises(TypeError):
        make_publisher(
            binding, "compiler-label", good[1], good[2], good[3], good[4]
        )
    with pytest.raises(TypeError):
        make_publisher(
            binding, good[0], good[1], good[2], "qualifier-label", good[4]
        )
    with pytest.raises(TypeError):
        make_publisher(binding, good[0], good[1], good[2], good[3], "pr-owner-label")


def test_binding_rejects_symlink_worktree_and_unqualified_branch(env, tmp_path):
    link = tmp_path / "clone-link"
    os.symlink(str(env.clone), str(link))
    with pytest.raises(ValueError):
        pub.PublisherBinding(
            worktree=str(link),
            expected_origin=str(env.origin),
            default_branch=DEFAULT_BRANCH,
            publisher_identity=PUBLISHER_IDENTITY,
        )
    with pytest.raises(ValueError):
        pub.PublisherBinding(
            worktree=str(env.clone),
            expected_origin=str(env.origin),
            default_branch="refs/heads/main",
            publisher_identity=PUBLISHER_IDENTITY,
        )
    with pytest.raises(ValueError):
        pub.PublisherBinding(
            worktree=str(env.clone),
            expected_origin=str(env.origin),
            default_branch=DEFAULT_BRANCH,
            publisher_identity=PUBLISHER_IDENTITY,
            repository="other-owner/other-repo",
        )


def test_proposal_envelope_contract_is_enforced(env):
    handle = build_publisher(env, expected_commit_of(env))
    envelope = handle.compiler(make_request())
    assert set(envelope.keys()) == {
        "schema",
        "state",
        "request_id",
        "request_sha256",
        "expected_commit",
        "work_ref",
        "path",
        "content_utf8",
        "content_sha256",
    }
    assert envelope["schema"] == "agentos.project_proposal.v1"
    assert envelope["state"] == "DRAFT_ONLY"
    assert envelope["path"] == CANONICAL_PATH
    assert len(envelope["request_id"]) <= 128
    assert envelope["request_id"].isascii()
    assert len(envelope["content_utf8"].encode("utf-8")) <= 32768
    assert envelope["content_sha256"] == hashlib.sha256(
        envelope["content_utf8"].encode("utf-8")
    ).hexdigest()
    assert envelope["request_sha256"] == hashlib.sha256(
        canonical_request_bytes(make_request())
    ).hexdigest()
    assert envelope["expected_commit"] == expected_commit_of(env)


def test_same_original_id_changed_payload_conflicts_without_new_refs_or_pr(env):
    handle = build_publisher(env, expected_commit_of(env))
    first = handle.publisher.publish(make_request(), AUTHORIZED_PRINCIPAL)
    assert first['state'] == 'PROPOSAL_PUBLISHED'
    before = snapshot(env.clone), snapshot(env.origin)
    changed = {**make_request(), 'summary': 'A different submitted request'}
    second = handle.publisher.publish(changed, AUTHORIZED_PRINCIPAL)
    assert second['state'] == 'CONFLICT'
    assert second['branch'] == first['branch']
    assert handle.pr_owner.create_calls == 1
    assert before == (snapshot(env.clone), snapshot(env.origin))


def test_pr_refusal_is_not_retried_on_same_original_publish(env):
    handle = build_publisher(env, expected_commit_of(env))
    handle.pr_owner.create_error = pub.PrOwnerRefused()
    first = handle.publisher.publish(make_request(), AUTHORIZED_PRINCIPAL)
    assert first['state'] == 'PREPARED' and first['reason'] == 'PR_CREATION_REFUSED'
    handle.pr_owner.create_error = None
    before = snapshot(env.clone), snapshot(env.origin)
    again = handle.publisher.publish(make_request(), AUTHORIZED_PRINCIPAL)
    assert again['state'] == 'PREPARED'
    assert handle.pr_owner.create_calls == 1
    assert before == (snapshot(env.clone), snapshot(env.origin))


def test_local_default_with_exact_project_is_not_upstream_creation(env):
    base = expected_commit_of(env)
    path = env.clone / CANONICAL_PATH
    path.parent.mkdir(parents=True)
    path.write_text(CONTENT)
    git(env.clone, 'add', CANONICAL_PATH)
    git(env.clone, 'commit', '-m', 'local project only')
    handle = build_publisher(env, base)
    result = handle.publisher.reconcile(make_request(), AUTHORIZED_PRINCIPAL)
    assert result['state'] == 'EFFECT_UNKNOWN'
    assert result['source'] is None
    assert handle.pr_owner.create_calls == 0


def test_distinct_pushurl_refuses_before_object_writes(env, tmp_path):
    handle = build_publisher(env, expected_commit_of(env))
    foreign = tmp_path / 'other.git'
    git(tmp_path, 'init', '--bare', str(foreign))
    git(env.clone, 'remote', 'set-url', '--push', 'origin', str(foreign))
    before = snapshot(env.clone), snapshot(env.origin), snapshot(foreign)
    result = handle.publisher.publish(make_request(), AUTHORIZED_PRINCIPAL)
    assert result['state'] == 'NOT_DISPATCHED' and result['reason'] == 'ORIGIN_MISMATCH'
    assert before == (snapshot(env.clone), snapshot(env.origin), snapshot(foreign))


def test_ambient_git_location_cannot_redirect_bound_publisher(env, tmp_path, monkeypatch):
    handle = build_publisher(env, expected_commit_of(env))
    foreign = tmp_path / 'foreign.git'
    git(tmp_path, 'init', '--bare', str(foreign))
    before = snapshot(foreign)
    with monkeypatch.context() as hostile:
        hostile.setenv('GIT_DIR', str(foreign))
        hostile.setenv('GIT_INDEX_FILE', str(tmp_path / 'hostile-index'))
        result = handle.publisher.publish(make_request(), AUTHORIZED_PRINCIPAL)
    assert result['state'] == 'PROPOSAL_PUBLISHED'
    assert not (tmp_path / 'hostile-index').exists()
    assert before == snapshot(foreign)


def test_revocation_at_first_object_write_creates_no_git_objects(env):
    handle = build_publisher(env, expected_commit_of(env))
    original = handle.publisher._build_commit
    def revoke(op, envelope, content):
        # Original auth source changes without replacing the captured seam.
        allowed[0] = False
        return original(op, envelope, content)
    allowed = [True]
    def gate(principal):
        return allowed[0] and authorize(principal)
    publisher = make_publisher(handle.binding, handle.compiler, gate, permission_stamp,
                              qualify_publisher, handle.pr_owner)
    original = publisher._build_commit
    publisher._build_commit = revoke
    before = snapshot(env.clone), snapshot(env.origin)
    result = publisher.publish(make_request(), AUTHORIZED_PRINCIPAL)
    assert result['state'] == 'NOT_DISPATCHED'
    assert before == (snapshot(env.clone), snapshot(env.origin))


# Retained independent reviewer reproductions.
def test_local_replace_ref_cannot_fabricate_upstream_project(env):
    expected = expected_commit_of(env)
    handle = build_publisher(env, expected)
    target = env.clone / CANONICAL_PATH
    target.parent.mkdir(parents=True)
    target.write_text(CONTENT)
    git(env.clone, 'add', CANONICAL_PATH)
    git(env.clone, 'commit', '-m', 'local spoof only')
    spoof = rev_parse(env.clone, 'HEAD')
    git(env.clone, 'replace', expected, spoof)
    assert git(env.origin, 'ls-tree', expected, '--', CANONICAL_PATH) == ''
    result = handle.publisher.publish(make_request(), AUTHORIZED_PRINCIPAL)
    assert result['state'] != 'PROJECT_CREATED', 'local replacement object was presented as actual upstream default content'

def test_revocation_at_final_read_cannot_false_clear_landed_publication(env):
    handle = build_publisher(env, expected_commit_of(env))
    checks = [0]
    def gate(principal):
        if handle.pr_owner.create_calls:
            checks[0] += 1
            if checks[0] > 1:
                return False
        return authorize(principal)
    publisher = make_publisher(handle.binding, handle.compiler, gate, permission_stamp,
                                 qualify_publisher, handle.pr_owner)
    result = publisher.publish(make_request(), AUTHORIZED_PRINCIPAL)
    assert handle.pr_owner.create_calls == 1
    assert rev_parse(env.origin, 'refs/heads/' + stable_branch()) is not None
    assert result['state'] == 'EFFECT_UNKNOWN', 'post-effect revocation was incorrectly reported NOT_DISPATCHED'
