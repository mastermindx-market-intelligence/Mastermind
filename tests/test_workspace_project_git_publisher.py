"""Real-Git negative and positive checks for ``workspace_project_git_publisher``.

Every test drives the actual ``git`` binary against a temporary bare remote and a
private clone.  There is no network access, no live GitHub call and no installed
service: the pull-request seam is an inert in-test object whose PR metadata lives
in the test object only, the proposal compiler is an explicit, fully authored
fixture that the parent joins to the actual canonical compiler later, and the
knowledge Events reader/claim validator is an inert in-test store whose retained
metadata and durable-phase claims live in the test object only.  Fixture recipe
mappings stand in for the actual private canonical compiler.

These are source-only unit tests.  A green run here is not a live publication
and is not proof of a live publication, a live Runtime claim or an installed
grant.
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
    return json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


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


# --------------------------------------------------------------------------- #
# Project-knowledge fixtures: inert private Events store and authored recipe
# mappings.  Retained metadata and durable-phase claims live in these TEST
# objects only; the parent joins the actual common Runtime Events engine and
# the actual private canonical recipe compiler later.
# --------------------------------------------------------------------------- #

import copy

KNOWLEDGE_SCHEMA = "mastermind.workspace_project_knowledge_publication.v1"
KNOWLEDGE_OPERATION_SCHEMA = "mastermind.workspace_project_knowledge_operation.v1"
KNOWLEDGE_RECIPE_SCHEMA = "mastermind.project_knowledge_recipe.v1"
KNOWLEDGE_FILE_REQUEST_SCHEMA = "mastermind.project_file_add_request.v1"
KNOWLEDGE_PREFERENCE_REQUEST_SCHEMA = "mastermind.project_preference_set_request.v1"
KNOWLEDGE_ACTION_FILE_ADD = "add_project_file"
KNOWLEDGE_ACTION_PREFERENCE = "set_project_communication_preference"

KNOWLEDGE_RESULT_KEYS = {
    "schema",
    "selection",
    "state",
    "recipe_fingerprint_sha256",
    "source",
    "proposal",
    "reason",
    "retryable",
}
KNOWLEDGE_LOOKUP_KEYS = {
    "action",
    "request_id",
    "work_ref",
    "source_commit",
    "base_revision",
    "request_sha256",
    "expected_preference_revision",
}
KNOWLEDGE_PUBLICATION_KEYS = {"repository", "commit", "postimages"}
KNOWLEDGE_PUBLICATION_IMAGE_KEYS = {"path", "content_sha256"}

FILE_ADD_REQUEST_ID = "mmos-project-file-add-" + "2" * 40
PREFERENCE_REQUEST_ID = "mmos-project-preference-set-" + "3" * 40
PERMISSION_BINDING_DIGEST = hashlib.sha256(
    b"fixture-knowledge-permission-binding"
).hexdigest()

FILE_DISPLAY_NAME = "notes.md"
FILE_CONTENT = (
    "# Demo project notes\n\n"
    "Authored project file content for the fixture upload.\n"
)

WORKSTREAM_TEXT = (
    "---\n"
    "schema: agentos.workstream.v1\n"
    "key: DEMO\n"
    "title: Demo workstream\n"
    "objective: Authored demo objective for the fixture workstream.\n"
    "program: build\n"
    "owner: fixture-owner\n"
    "next_action: Await review\n"
    "status: active\n"
    "class: build\n"
    "blast_radius: reversible\n"
    "ambiguity: specified\n"
    "repos:\n"
    "- macro\n"
    "waves:\n"
    "- name: wave-1\n"
    "decisions: []\n"
    "artifacts: []\n"
    "project_files: []\n"
    "---\n"
    "Authored workstream record body for fixture preimages.\n"
)

DECISION_TEXT_V1 = (
    "---\n"
    "schema: agentos.decision.v1\n"
    "key: PROJECT-COMMUNICATION-PREFERENCE-DEMO\n"
    "question: How should this project communicate with its owner?\n"
    "answer: Weekly digest\n"
    "rationale: Explicit project-scoped communication preference supplied through the authorized project editor.\n"
    "alternatives:\n"
    "- option: Leave the preference unset\n"
    "  why_not: The authorized editor requested this value.\n"
    "evidence:\n"
    "- project-authoring-request:" + "0" * 64 + "\n"
    "affects:\n"
    "- WS:DEMO\n"
    "confidence: high\n"
    "reversibility: easy\n"
    "decided_by: workspace:fixture\n"
    "decided_at: 2026-01-01\n"
    "project_preference:\n"
    "  schema: agentos.project_preference.v1\n"
    "  work_ref: WS:DEMO\n"
    "  kind: COMMUNICATION\n"
    "  value: Weekly digest\n"
    "  origin:\n"
    "    kind: USER_EDIT\n"
    "    actor_ref: workspace:fixture\n"
    "    source_ref: null\n"
    "    source_revision: null\n"
    "  last_edit:\n"
    "    actor_ref: workspace:fixture\n"
    "    request_sha256: " + "0" * 64 + "\n"
    "---\n"
)

WS_DECISIONS_POINTER = "- DEC:PROJECT-COMMUNICATION-PREFERENCE-DEMO\n"


def sha_hex(text):
    raw = text.encode("utf-8") if isinstance(text, str) else text
    return hashlib.sha256(raw).hexdigest()


def scope_of(principal):
    return hashlib.sha256(principal.subject.encode("utf-8")).hexdigest()


def knowledge_branch(request, principal=AUTHORIZED_PRINCIPAL):
    action = (
        KNOWLEDGE_ACTION_FILE_ADD
        if request["schema"] == KNOWLEDGE_FILE_REQUEST_SCHEMA
        else KNOWLEDGE_ACTION_PREFERENCE
    )
    identity = {
        "principal_scope": scope_of(principal),
        "action": action,
        "request_id": request["request_id"],
    }
    return "mmos/knowledge-" + hashlib.sha256(
        canonical_request_bytes(identity)
    ).hexdigest()


def knowledge_lookup(request, principal=AUTHORIZED_PRINCIPAL):
    action = (
        KNOWLEDGE_ACTION_FILE_ADD
        if request["schema"] == KNOWLEDGE_FILE_REQUEST_SCHEMA
        else KNOWLEDGE_ACTION_PREFERENCE
    )
    return {
        "action": action,
        "request_id": request["request_id"],
        "work_ref": request["work_ref"],
        "source_commit": request["source_commit"],
        "base_revision": request["base_revision"],
        "request_sha256": hashlib.sha256(
            canonical_request_bytes(request)
        ).hexdigest(),
        "expected_preference_revision": request.get("expected_preference_revision"),
    }


def knowledge_stamp_for(principal, action, work_ref):
    return hashlib.sha256(canonical_request_bytes({"principal_scope":scope_of(principal),
        "action":action,"work_ref":work_ref})).hexdigest()


def recipe_envelope(request, action, fingerprint, postimages, principal=AUTHORIZED_PRINCIPAL):
    return {
        "schema": KNOWLEDGE_RECIPE_SCHEMA,
        "state": "DRAFT_ONLY",
        "action": (
            "project_file_add"
            if action == KNOWLEDGE_ACTION_FILE_ADD
            else "project_preference_set"
        ),
        "work_ref": request["work_ref"],
        "request_id": request["request_id"],
        "request_fingerprint": fingerprint,
        "captured_commit": request["source_commit"],
        "permission_binding_digest": knowledge_stamp_for(principal,action,request["work_ref"]),
        "postimages": postimages,
    }


def fixture_fingerprint(seed, request):
    return hashlib.sha256(
        canonical_request_bytes({"fixture": seed, "request_id": request["request_id"]})
    ).hexdigest()


def build_file_add_recipe(
    request,
    principal=AUTHORIZED_PRINCIPAL,
    *,
    file_content=FILE_CONTENT,
    ws_preimage_text=WORKSTREAM_TEXT,
    fingerprint_seed="file-add",
):
    """Authored fixture mapping of the private canonical file-add compiler."""
    scope = scope_of(principal)
    file_id = hashlib.sha256(
        canonical_request_bytes(
            {
                "principal_scope": scope,
                "request_id": request["request_id"],
                "work_ref": request["work_ref"],
            }
        )
    ).hexdigest()
    key = request["work_ref"][3:]
    media_path = "agentos/project-files/WS-%s/%s.md" % (key, file_id)
    ws_path = "agentos/workstreams/WS-%s.md" % key
    fingerprint = fixture_fingerprint(fingerprint_seed, request)
    content_sha256 = sha_hex(file_content)
    entry = (
        "project_files:\n"
        "- file_id: " + file_id + "\n"
        "  artifact_ref: " + media_path + "\n"
        "  display_name: " + FILE_DISPLAY_NAME + "\n"
        "  media_type: text/markdown\n"
        "  content_sha256: " + content_sha256 + "\n"
        "  origin:\n"
        "    kind: PRINCIPAL_UPLOAD\n"
        "    actor_ref: workspace:" + scope + "\n"
        "    request_sha256: " + fingerprint + "\n"
    )
    ws_post = ws_preimage_text.replace("project_files: []\n", entry)
    postimages = [
        {
            "path": media_path,
            "content_utf8": file_content,
            "content_sha256": content_sha256,
            "expected_preimage_sha256": None,
        },
        {
            "path": ws_path,
            "content_utf8": ws_post,
            "content_sha256": sha_hex(ws_post),
            "expected_preimage_sha256": sha_hex(ws_preimage_text),
        },
    ]
    return recipe_envelope(
        request, KNOWLEDGE_ACTION_FILE_ADD, fingerprint, postimages, principal=principal
    )


def build_preference_recipe(
    request,
    principal=AUTHORIZED_PRINCIPAL,
    *,
    value,
    decision_preimage_text=None,
    decision_post_text=None,
    ws_preimage_text=WORKSTREAM_TEXT,
    fingerprint_seed="preference",
):
    """Authored fixture mapping of the private canonical preference compiler.

    ``decision_preimage_text`` ``None`` means a new fixed-key record; the
    workstream postimage gains the decisions pointer.  With a preimage the
    workstream record is left byte-identical (an edit with unchanged WS).
    """
    key = request["work_ref"][3:]
    dec_path = "agentos/decisions/DEC-PROJECT-COMMUNICATION-PREFERENCE-%s.md" % key
    ws_path = "agentos/workstreams/WS-%s.md" % key
    fingerprint = fixture_fingerprint(fingerprint_seed, request)
    if decision_preimage_text is None:
        decision_preimage = None
        if decision_post_text is None:
            decision_post_text = (
                "---\n"
                "schema: agentos.decision.v1\n"
                "key: PROJECT-COMMUNICATION-PREFERENCE-DEMO\n"
                "question: How should this project communicate with its owner?\n"
                "answer: " + value + "\n"
                "rationale: Explicit project-scoped communication preference supplied through the authorized project editor.\n"
                "alternatives:\n"
                "- option: Leave the preference unset\n"
                "  why_not: The authorized editor requested this value.\n"
                "evidence:\n"
                "- project-authoring-request:" + fingerprint + "\n"
                "affects:\n"
                "- WS:DEMO\n"
                "confidence: high\n"
                "reversibility: easy\n"
                "decided_by: workspace:" + scope_of(principal) + "\n"
                "decided_at: 2026-02-02\n"
                "project_preference:\n"
                "  schema: agentos.project_preference.v1\n"
                "  work_ref: WS:DEMO\n"
                "  kind: COMMUNICATION\n"
                "  value: " + value + "\n"
                "  origin:\n"
                "    kind: USER_EDIT\n"
                "    actor_ref: workspace:" + scope_of(principal) + "\n"
                "    source_ref: null\n"
                "    source_revision: null\n"
                "  last_edit:\n"
                "    actor_ref: workspace:" + scope_of(principal) + "\n"
                "    request_sha256: " + fingerprint + "\n"
                "---\n"
            )
        ws_post = ws_preimage_text.replace(
            "decisions: []\n", "decisions:\n" + WS_DECISIONS_POINTER
        )
    else:
        decision_preimage = sha_hex(decision_preimage_text)
        if decision_post_text is None:
            decision_post_text = decision_preimage_text.replace(
                "answer: Weekly digest", "answer: " + value
            )
        ws_post = ws_preimage_text
    postimages = [
        {
            "path": dec_path,
            "content_utf8": decision_post_text,
            "content_sha256": sha_hex(decision_post_text),
            "expected_preimage_sha256": decision_preimage,
        },
        {
            "path": ws_path,
            "content_utf8": ws_post,
            "content_sha256": sha_hex(ws_post),
            "expected_preimage_sha256": sha_hex(ws_preimage_text),
        },
    ]
    return recipe_envelope(
        request, KNOWLEDGE_ACTION_PREFERENCE, fingerprint, postimages, principal=principal
    )


class KnowledgeClaim:
    """Inert durable-phase-CAS permit fixture (never a public serialized claim)."""

    def __init__(self, token):
        self.token = token


class KnowledgeOperationEvents:
    """Inert private common-Runtime Events reader/claim validator fixture.

    Real retained metadata and the real private claim live in this TEST object
    only; nothing here talks to an installed Runtime.
    """

    def __init__(self):
        self.operations = {}
        self.load_calls = 0
        self.validate_calls = 0

    def record(self, principal, request, recipe, *, phase="CLAIMED", claim=None):
        lookup = knowledge_lookup(request, principal)
        claim = claim or KnowledgeClaim("claim-" + request["request_id"][-8:])
        metadata = {
            "schema": KNOWLEDGE_OPERATION_SCHEMA,
            "identity": dict(lookup, principal_scope=scope_of(principal)),
            "recipe_fingerprint_sha256": recipe["request_fingerprint"],
            "permission_binding_digest": recipe["permission_binding_digest"],
            "phase": phase,
            "expected_commit": lookup["source_commit"],
            "postimages": [
                {
                    "path": image["path"],
                    "content_sha256": image["content_sha256"],
                    "expected_preimage_sha256": image["expected_preimage_sha256"],
                }
                for image in recipe["postimages"]
            ],
            "branch": None,
            "publication": None,
            "proposal": None,
        }
        self.operations[(principal.subject, lookup["action"], lookup["request_id"])] = {
            "metadata": metadata,
            "claim": claim,
        }
        return claim

    def load_original_operation(self, principal, lookup):
        self.load_calls += 1
        entry = self.operations.get(
            (principal.subject, lookup["action"], lookup["request_id"])
        )
        if entry is None:
            return None
        return copy.deepcopy(entry["metadata"])

    def validate_original_claim(self, principal, lookup, claim, metadata):
        self.validate_calls += 1
        entry = self.operations.get(
            (principal.subject, lookup["action"], lookup["request_id"])
        )
        if entry is None:
            return False
        if claim is not entry["claim"]:
            return False
        return metadata.get("phase") == "CLAIMED"

    def authorize_knowledge(self, principal, action, work_ref):
        return (
            isinstance(principal, Principal)
            and action in (KNOWLEDGE_ACTION_FILE_ADD, KNOWLEDGE_ACTION_PREFERENCE)
            and isinstance(work_ref, str)
            and work_ref.startswith("WS:")
        )

    def knowledge_permission_stamp(self, principal, action, work_ref):
        return knowledge_stamp_for(principal,action,work_ref)


def seed_preimages(env, files):
    """Author and push preimage records on the upstream default branch."""
    for path, text in files.items():
        target = env.clone / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        git(env.clone, "add", path)
    git(env.clone, "commit", "-m", "seed knowledge preimages")
    git(env.clone, "push", "origin", DEFAULT_BRANCH)
    return expected_commit_of(env)


def make_file_add_request(
    source_commit,
    *,
    request_id=FILE_ADD_REQUEST_ID,
    work_ref=WORK_REF,
    content=FILE_CONTENT,
    display_name=FILE_DISPLAY_NAME,
    base_revision=None,
):
    return {
        "schema": KNOWLEDGE_FILE_REQUEST_SCHEMA,
        "request_id": request_id,
        "work_ref": work_ref,
        "source_commit": source_commit,
        "base_revision": base_revision or sha_hex(WORKSTREAM_TEXT),
        "file": {
            "display_name": display_name,
            "media_type": "text/markdown",
            "content_utf8": content,
        },
    }


def make_preference_request(
    source_commit,
    *,
    request_id=PREFERENCE_REQUEST_ID,
    work_ref=WORK_REF,
    value="Daily brief",
    expected_preference_revision=None,
    base_revision=None,
):
    return {
        "schema": KNOWLEDGE_PREFERENCE_REQUEST_SCHEMA,
        "request_id": request_id,
        "work_ref": work_ref,
        "source_commit": source_commit,
        "base_revision": base_revision or sha_hex(WORKSTREAM_TEXT),
        "expected_preference_revision": expected_preference_revision,
        "value": value,
    }


def build_knowledge_publisher(
    env,
    *,
    events=None,
    pr_owner=None,
    expected_origin=None,
    authorize_knowledge=None,
    knowledge_permission_stamp=None,
    validate_original_claim=None,
):
    events = events or KnowledgeOperationEvents()
    pr_owner = pr_owner or InertPullRequestOwner(env.origin)
    binding = pub.PublisherBinding(
        worktree=str(env.clone),
        expected_origin=expected_origin or str(env.origin),
        default_branch=DEFAULT_BRANCH,
        publisher_identity=PUBLISHER_IDENTITY,
    )
    # The CREATE compiler fixture stands in for the CREATE surface only; the
    # knowledge path must never call it.
    compiler = AuthoredProposalCompiler(expected_commit_of(env))
    publisher = make_publisher(
        binding,
        compiler,
        authorize,
        permission_stamp,
        qualify_publisher,
        pr_owner,
        authorize_knowledge=authorize_knowledge or events.authorize_knowledge,
        knowledge_permission_stamp=(
            knowledge_permission_stamp or events.knowledge_permission_stamp
        ),
        load_original_operation=events.load_original_operation,
        validate_original_claim=(
            validate_original_claim or events.validate_original_claim
        ),
    )
    return SimpleNamespace(
        publisher=publisher,
        binding=binding,
        compiler=compiler,
        pr_owner=pr_owner,
        events=events,
    )


def assert_closed_knowledge_result(result):
    assert set(result.keys()) == KNOWLEDGE_RESULT_KEYS
    assert result["schema"] == KNOWLEDGE_SCHEMA
    assert result["state"] in pub.KNOWLEDGE_STATES
    assert result["retryable"] is False
    if result["selection"] is not None:
        assert set(result["selection"].keys()) == KNOWLEDGE_LOOKUP_KEYS
    assert result["recipe_fingerprint_sha256"] is None or (
        len(result["recipe_fingerprint_sha256"]) == 64
    )
    if result["source"] is not None:
        assert set(result["source"].keys()) == KNOWLEDGE_PUBLICATION_KEYS
        assert len(result["source"]["postimages"]) == 2
        for image in result["source"]["postimages"]:
            assert set(image.keys()) == KNOWLEDGE_PUBLICATION_IMAGE_KEYS
    if result["proposal"] is not None:
        assert set(result["proposal"].keys()) == RECEIPT_KEYS


# --------------------------------------------------------------------------- #
# Knowledge positive paths
# --------------------------------------------------------------------------- #


def knowledge_file_add_setup(env):
    base = seed_preimages(env, {CANONICAL_PATH: WORKSTREAM_TEXT})
    request = make_file_add_request(base)
    recipe = build_file_add_recipe(request)
    handle = build_knowledge_publisher(env)
    claim = handle.events.record(AUTHORIZED_PRINCIPAL, request, recipe)
    return handle, request, recipe, claim


def test_knowledge_file_add_publishes_one_atomic_commit_and_single_pr(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    before_clone = snapshot(env.clone)
    before_origin = snapshot(env.origin)
    default_before = rev_parse(env.clone, "refs/heads/" + DEFAULT_BRANCH)

    result = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "PROPOSAL_PUBLISHED"
    assert result["selection"] == knowledge_lookup(request)
    assert result["recipe_fingerprint_sha256"] == recipe["request_fingerprint"]
    assert result["reason"] is None and result["source"] is None
    branch = knowledge_branch(request)
    assert result["selection"]["request_id"] == request["request_id"]
    assert result["selection"]["action"] == KNOWLEDGE_ACTION_FILE_ADD
    receipt = result["proposal"]
    remote_commit = rev_parse(env.origin, "refs/heads/" + branch)
    assert remote_commit is not None, "knowledge branch must be on the verified origin"
    assert receipt["head_commit"] == remote_commit
    assert receipt["head_branch"] == branch
    assert receipt["url"] == "https://github.com/%s/pull/%d" % (
        REPOSITORY,
        receipt["number"],
    )

    # Exactly one atomic commit, one parent, both logical postimages.
    parents = git(env.clone, "rev-list", "--parents", "-n", "1", remote_commit).split()
    assert parents == [remote_commit, default_before]
    delta = sorted(
        line
        for line in git(env.clone, "diff-tree", "-r", "--no-commit-id", "--name-only", remote_commit).splitlines()
        if line
    )
    media_path, ws_path = (
        image["path"] for image in recipe["postimages"]
    )
    assert delta == sorted([media_path, ws_path])
    media_blob = git(env.clone, "cat-file", "blob", "%s:%s" % (remote_commit, media_path))
    assert media_blob == FILE_CONTENT
    ws_blob = git(env.clone, "cat-file", "blob", "%s:%s" % (remote_commit, ws_path))
    assert ws_blob == recipe["postimages"][1]["content_utf8"]
    assert sha_hex(media_blob) == recipe["postimages"][0]["content_sha256"]
    assert sha_hex(ws_blob) == recipe["postimages"][1]["content_sha256"]

    # Default branch untouched; exactly one PR; no CREATE compiler call.
    assert rev_parse(env.origin, "refs/heads/" + DEFAULT_BRANCH) == default_before
    assert len(handle.pr_owner.pull_requests) == 1
    assert handle.pr_owner.create_calls == 1
    assert handle.compiler.requests_seen == []
    assert before_clone != snapshot(env.clone), "stable local branch ref is created"
    assert before_origin != snapshot(env.origin), "branch pushed to the verified origin"


def test_knowledge_file_add_merged_readback_is_source_published(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    published = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )
    assert published["state"] == "PROPOSAL_PUBLISHED"
    branch = knowledge_branch(request)

    # Someone else performs the normal protected merge (never this publisher).
    integrator = env.tmp_path / "integrator"
    git(env.tmp_path, "clone", str(env.origin), str(integrator))
    git(integrator, "fetch", "origin", branch)
    git(integrator, "checkout", "-q", DEFAULT_BRANCH)
    git(integrator, "merge", "--no-ff", "--no-edit", "FETCH_HEAD")
    git(integrator, "push", "origin", DEFAULT_BRANCH)
    merged_commit = rev_parse(env.origin, "refs/heads/" + DEFAULT_BRANCH)

    result = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "SOURCE_PUBLISHED"
    assert result["source"]["repository"] == REPOSITORY
    assert result["source"]["commit"] == merged_commit
    assert sorted(
        (image["path"], image["content_sha256"])
        for image in result["source"]["postimages"]
    ) == sorted(
        (image["path"], image["content_sha256"])
        for image in recipe["postimages"]
    )
    # One verified tree actually carries both canonical postimages.
    for image in recipe["postimages"]:
        blob = git(
            integrator, "cat-file", "blob", "%s:%s" % (merged_commit, image["path"])
        )
        assert sha_hex(blob) == image["content_sha256"]
    assert handle.pr_owner.create_calls == 1, "no second PR"


def test_knowledge_reconcile_after_merge_is_source_published_readonly(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    published = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )
    branch = knowledge_branch(request)
    integrator = env.tmp_path / "integrator"
    git(env.tmp_path, "clone", str(env.origin), str(integrator))
    git(integrator, "fetch", "origin", branch)
    git(integrator, "checkout", "-q", DEFAULT_BRANCH)
    git(integrator, "merge", "--no-ff", "--no-edit", "FETCH_HEAD")
    git(integrator, "push", "origin", DEFAULT_BRANCH)
    merged_commit = rev_parse(env.origin, "refs/heads/" + DEFAULT_BRANCH)
    create_calls = handle.pr_owner.create_calls
    before_clone_refs = refs(env.clone)
    before_origin = snapshot(env.origin)

    reconciled = handle.publisher.reconcile_knowledge(
        knowledge_lookup(request), AUTHORIZED_PRINCIPAL
    )

    assert_closed_knowledge_result(reconciled)
    assert reconciled["state"] == "SOURCE_PUBLISHED"
    assert reconciled["source"]["commit"] == merged_commit
    assert reconciled["selection"] == knowledge_lookup(request)
    assert reconciled["recipe_fingerprint_sha256"] == recipe["request_fingerprint"]
    assert handle.pr_owner.create_calls == create_calls, "reconcile never creates"
    # Reconcile may fetch the exact observed commit (no refs/FETCH_HEAD), but
    # it never creates refs or publication objects.
    assert refs(env.clone) == before_clone_refs
    assert_unchanged(before_origin, env.origin)


def test_knowledge_preference_new_record_changes_both_paths(env):
    base = seed_preimages(env, {CANONICAL_PATH: WORKSTREAM_TEXT})
    request = make_preference_request(base)
    recipe = build_preference_recipe(request, value="Daily brief")
    handle = build_knowledge_publisher(env)
    claim = handle.events.record(AUTHORIZED_PRINCIPAL, request, recipe)

    result = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "PROPOSAL_PUBLISHED"
    branch = knowledge_branch(request)
    remote_commit = rev_parse(env.origin, "refs/heads/" + branch)
    delta = sorted(
        line
        for line in git(env.clone, "diff-tree", "-r", "--no-commit-id", "--name-only", remote_commit).splitlines()
        if line
    )
    dec_path, ws_path = (image["path"] for image in recipe["postimages"])
    assert delta == sorted([dec_path, ws_path]), "new record changes both paths"
    assert git(env.clone, "cat-file", "blob", "%s:%s" % (remote_commit, dec_path)) == (
        recipe["postimages"][0]["content_utf8"]
    )


def test_knowledge_preference_edit_leaves_workstream_unchanged(env):
    base = seed_preimages(
        env, {CANONICAL_PATH: WORKSTREAM_TEXT, recipe_dec_path(): DECISION_TEXT_V1}
    )
    request = make_preference_request(
        base, expected_preference_revision=sha_hex(DECISION_TEXT_V1)
    )
    recipe = build_preference_recipe(
        request,
        value="Daily brief",
        decision_preimage_text=DECISION_TEXT_V1,
    )
    handle = build_knowledge_publisher(env)
    claim = handle.events.record(AUTHORIZED_PRINCIPAL, request, recipe)
    before_default = rev_parse(env.origin, "refs/heads/" + DEFAULT_BRANCH)

    result = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "PROPOSAL_PUBLISHED"
    branch = knowledge_branch(request)
    remote_commit = rev_parse(env.origin, "refs/heads/" + branch)
    parents = git(env.clone, "rev-list", "--parents", "-n", "1", remote_commit).split()
    assert parents == [remote_commit, base]
    delta = [
        line
        for line in git(env.clone, "diff-tree", "-r", "--no-commit-id", "--name-only", remote_commit).splitlines()
        if line
    ]
    dec_path, ws_path = (image["path"] for image in recipe["postimages"])
    assert delta == [dec_path], "preference edit may leave the workstream unchanged"
    ws_blob = git(env.clone, "cat-file", "blob", "%s:%s" % (remote_commit, ws_path))
    assert ws_blob == WORKSTREAM_TEXT, "workstream bytes unchanged by the edit"
    assert rev_parse(env.origin, "refs/heads/" + DEFAULT_BRANCH) == before_default
    assert handle.pr_owner.create_calls == 1


def recipe_dec_path():
    return "agentos/decisions/DEC-PROJECT-COMMUNICATION-PREFERENCE-DEMO.md"


def fixture_media_path(request, principal=AUTHORIZED_PRINCIPAL):
    """The deterministic fixture media path for a file-add request."""
    file_id = hashlib.sha256(
        canonical_request_bytes(
            {
                "principal_scope": scope_of(principal),
                "request_id": request["request_id"],
                "work_ref": request["work_ref"],
            }
        )
    ).hexdigest()
    key = request["work_ref"][3:]
    return "agentos/project-files/WS-%s/%s.md" % (key, file_id)


# --------------------------------------------------------------------------- #
# Knowledge denials before any publication object
# --------------------------------------------------------------------------- #


def test_knowledge_missing_operation_denies_without_writes(env):
    base = seed_preimages(env, {CANONICAL_PATH: WORKSTREAM_TEXT})
    request = make_file_add_request(base)
    recipe = build_file_add_recipe(request)
    handle = build_knowledge_publisher(env)
    claim = KnowledgeClaim("unrecorded-claim")
    before = snapshot(env.clone), snapshot(env.origin)

    result = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "NOT_DISPATCHED"
    assert result["reason"] == "OPERATION_MISSING"
    assert result["source"] is None and result["proposal"] is None
    assert handle.pr_owner.create_calls == 0
    assert before == (snapshot(env.clone), snapshot(env.origin))


def test_knowledge_foreign_retained_identity_conflicts_without_writes(env):
    base = seed_preimages(env, {CANONICAL_PATH: WORKSTREAM_TEXT})
    request = make_file_add_request(base)
    recipe = build_file_add_recipe(request)
    handle = build_knowledge_publisher(env)
    claim = handle.events.record(AUTHORIZED_PRINCIPAL, request, recipe)
    # The retained operation belongs to a different original target/commit.
    stored = handle.events.operations[
        (AUTHORIZED_PRINCIPAL.subject, KNOWLEDGE_ACTION_FILE_ADD, request["request_id"])
    ]
    stored["metadata"]["identity"]["source_commit"] = "b" * 40
    stored["metadata"]["expected_commit"] = "b" * 40
    before = snapshot(env.clone), snapshot(env.origin)

    result = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "CONFLICT"
    assert result["reason"] in ("OPERATION_INVALID", "OPERATION_CONFLICT")
    assert handle.pr_owner.create_calls == 0
    assert before == (snapshot(env.clone), snapshot(env.origin))


def test_knowledge_changed_work_ref_is_conflict_not_new_branch(env):
    base = seed_preimages(env, {CANONICAL_PATH: WORKSTREAM_TEXT})
    request = make_file_add_request(base)
    recipe = build_file_add_recipe(request)
    handle = build_knowledge_publisher(env)
    claim = handle.events.record(AUTHORIZED_PRINCIPAL, request, recipe)
    before = snapshot(env.clone), snapshot(env.origin)
    # Same original request id, changed work: a recipe consistent with the
    # moved request still conflicts against the retained identity, and no
    # second branch is ever created for it.
    moved = dict(request, work_ref="WS:OTHER")
    moved_recipe = build_file_add_recipe(moved)
    result = handle.publisher.publish_knowledge(
        moved, moved_recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "CONFLICT"
    assert result["reason"] == "OPERATION_CONFLICT"
    assert before == (snapshot(env.clone), snapshot(env.origin))
    assert rev_parse(env.origin, "refs/heads/" + knowledge_branch(moved)) is None


def test_knowledge_wrong_claim_denies_before_writes(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    before = snapshot(env.clone), snapshot(env.origin)

    result = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=KnowledgeClaim("other-permit")
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "NOT_DISPATCHED"
    assert result["reason"] == "CLAIM_INVALID"
    assert handle.pr_owner.create_calls == 0
    assert before == (snapshot(env.clone), snapshot(env.origin))


def test_knowledge_changed_public_payload_under_same_id_conflicts(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    first = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )
    assert first["state"] == "PROPOSAL_PUBLISHED"
    before = snapshot(env.clone), snapshot(env.origin)
    changed = make_file_add_request(
        request["source_commit"], content="# Different authored file content\n"
    )

    result = handle.publisher.publish_knowledge(
        changed, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "CONFLICT"
    assert result["reason"] == "OPERATION_CONFLICT"
    assert before == (snapshot(env.clone), snapshot(env.origin))
    assert handle.pr_owner.create_calls == 1


def test_knowledge_changed_private_fingerprint_conflicts(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    other = build_file_add_recipe(request, fingerprint_seed="other-compiler-run")
    assert other["request_fingerprint"] != recipe["request_fingerprint"]
    before = snapshot(env.clone), snapshot(env.origin)

    result = handle.publisher.publish_knowledge(
        request, other, AUTHORIZED_PRINCIPAL, claim=claim
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "CONFLICT"
    assert result["reason"] == "OPERATION_CONFLICT"
    assert before == (snapshot(env.clone), snapshot(env.origin))


def test_knowledge_changed_old_workstream_preimage_conflicts(env):
    base = seed_preimages(env, {CANONICAL_PATH: WORKSTREAM_TEXT})
    request = make_file_add_request(base)
    recipe = build_file_add_recipe(request)
    handle = build_knowledge_publisher(env)
    claim = handle.events.record(AUTHORIZED_PRINCIPAL, request, recipe)
    # The actual upstream preimage differs from the captured one.
    diverged = seed_preimages(env, {CANONICAL_PATH: WORKSTREAM_TEXT + "appended\n"})
    assert diverged != base
    before = snapshot(env.clone), snapshot(env.origin)

    result = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "NOT_DISPATCHED"
    assert result["reason"] == "STALE_EXPECTED_COMMIT"
    assert before == (snapshot(env.clone), snapshot(env.origin))


def test_knowledge_changed_old_decision_preimage_conflicts(env):
    base = seed_preimages(
        env,
        {CANONICAL_PATH: WORKSTREAM_TEXT, recipe_dec_path(): DECISION_TEXT_V1 + "edited upstream\n"},
    )
    request = make_preference_request(
        base, expected_preference_revision=sha_hex(DECISION_TEXT_V1)
    )
    recipe = build_preference_recipe(
        request, value="Daily brief", decision_preimage_text=DECISION_TEXT_V1
    )
    handle = build_knowledge_publisher(env)
    claim = handle.events.record(AUTHORIZED_PRINCIPAL, request, recipe)
    before = snapshot(env.clone), snapshot(env.origin)

    result = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "CONFLICT"
    assert result["reason"] == "PREIMAGE_CONFLICT"
    assert before == (snapshot(env.clone), snapshot(env.origin))


def test_knowledge_stale_upstream_commit_denies_before_objects(env):
    base = seed_preimages(env, {CANONICAL_PATH: WORKSTREAM_TEXT})
    request = make_file_add_request(base)
    recipe = build_file_add_recipe(request)
    handle = build_knowledge_publisher(env)
    claim = handle.events.record(AUTHORIZED_PRINCIPAL, request, recipe)
    later = seed_preimages(env, {"agentos/notes/unrelated.txt": "unrelated\n"})
    assert later != base
    before = snapshot(env.clone), snapshot(env.origin)

    result = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "NOT_DISPATCHED"
    assert result["reason"] == "STALE_EXPECTED_COMMIT"
    assert before == (snapshot(env.clone), snapshot(env.origin))


def test_knowledge_media_path_collision_in_base_denies(env):
    media_path = fixture_media_path(
        make_file_add_request("0" * 40)
    )
    base = seed_preimages(
        env, {CANONICAL_PATH: WORKSTREAM_TEXT, media_path: "already recorded\n"}
    )
    request = make_file_add_request(base)
    recipe = build_file_add_recipe(request)
    handle = build_knowledge_publisher(env)
    claim = handle.events.record(AUTHORIZED_PRINCIPAL, request, recipe)
    media_path = recipe["postimages"][0]["path"]
    assert base == expected_commit_of(env)
    before = snapshot(env.clone), snapshot(env.origin)

    result = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "NOT_DISPATCHED"
    assert result["reason"] == "PATH_COLLISION_IN_BASE"
    assert before == (snapshot(env.clone), snapshot(env.origin))


def test_knowledge_malformed_request_denies(env):
    base = seed_preimages(env, {CANONICAL_PATH: WORKSTREAM_TEXT})
    handle = build_knowledge_publisher(env)
    before = snapshot(env.clone), snapshot(env.origin)
    wrong_schema = make_file_add_request(base)
    wrong_schema["schema"] = "mastermind.project_preference_set_request.v1"
    for broken in (
        wrong_schema,
        make_file_add_request(base, request_id="mmos-project-create-" + "2" * 40),
        dict(make_file_add_request(base), unexpected="field"),
        make_file_add_request(base, display_name="../../evil.sh"),
        make_file_add_request(base, content="x" * 40000),
    ):
        recipe = build_file_add_recipe(broken)
        claim = handle.events.record(AUTHORIZED_PRINCIPAL, broken, recipe)
        result = handle.publisher.publish_knowledge(
            broken, recipe, AUTHORIZED_PRINCIPAL, claim=claim
        )
        assert_closed_knowledge_result(result)
        assert result["state"] == "NOT_DISPATCHED"
        assert result["reason"] == "REQUEST_INVALID"
    assert before == (snapshot(env.clone), snapshot(env.origin))
    assert handle.pr_owner.create_calls == 0


def test_knowledge_recipe_not_binding_actual_request_denies(env):
    base = seed_preimages(env, {CANONICAL_PATH: WORKSTREAM_TEXT})
    handle = build_knowledge_publisher(env)
    before = snapshot(env.clone), snapshot(env.origin)
    request = make_file_add_request(base)
    # Recipe postimages drift from the actual public request content.
    recipe = build_file_add_recipe(request, file_content="# Other content\n")
    claim = handle.events.record(AUTHORIZED_PRINCIPAL, request, recipe)

    result = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "NOT_DISPATCHED"
    assert result["reason"] == "RECIPE_INVALID"
    assert before == (snapshot(env.clone), snapshot(env.origin))


def test_knowledge_recipe_with_third_path_or_bad_digest_denies(env):
    base = seed_preimages(env, {CANONICAL_PATH: WORKSTREAM_TEXT})
    handle = build_knowledge_publisher(env)
    before = snapshot(env.clone), snapshot(env.origin)
    request = make_file_add_request(base)
    recipe = build_file_add_recipe(request)
    claim = handle.events.record(AUTHORIZED_PRINCIPAL, request, recipe)
    drifted = copy.deepcopy(recipe)
    drifted["postimages"][1]["content_sha256"] = "f" * 64
    third_path = copy.deepcopy(recipe)
    third_path["postimages"][0]["path"] = "agentos/project-files/WS-DEMO/evil.md"
    for broken in (drifted, third_path):
        result = handle.publisher.publish_knowledge(
            request, broken, AUTHORIZED_PRINCIPAL, claim=claim
        )
        assert_closed_knowledge_result(result)
        assert result["state"] in ("NOT_DISPATCHED", "CONFLICT")
        assert result["reason"] in ("RECIPE_INVALID", "OPERATION_CONFLICT")
    assert before == (snapshot(env.clone), snapshot(env.origin))


# --------------------------------------------------------------------------- #
# Knowledge seam absence, phase gating and exactly-once boundaries
# --------------------------------------------------------------------------- #


def test_knowledge_absent_seams_deny_without_create_fallback(env):
    base = seed_preimages(env, {CANONICAL_PATH: WORKSTREAM_TEXT})
    request = make_file_add_request(base)
    recipe = build_file_add_recipe(request)
    binding = pub.PublisherBinding(
        worktree=str(env.clone),
        expected_origin=str(env.origin),
        default_branch=DEFAULT_BRANCH,
        publisher_identity=PUBLISHER_IDENTITY,
    )
    # The CREATE authorizer grants; there is no knowledge seam at all.
    publisher = make_publisher(
        binding,
        AuthoredProposalCompiler(base),
        authorize,
        permission_stamp,
        qualify_publisher,
        InertPullRequestOwner(env.origin),
    )
    before = snapshot(env.clone), snapshot(env.origin)

    result = publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=KnowledgeClaim("x")
    )
    assert_closed_knowledge_result(result)
    assert result["state"] == "NOT_DISPATCHED"
    assert result["reason"] == "KNOWLEDGE_SEAMS_ABSENT"
    reconciled = publisher.reconcile_knowledge(
        knowledge_lookup(request), AUTHORIZED_PRINCIPAL
    )
    assert_closed_knowledge_result(reconciled)
    assert reconciled["state"] == "NOT_DISPATCHED"
    assert reconciled["reason"] == "KNOWLEDGE_SEAMS_ABSENT"
    assert before == (snapshot(env.clone), snapshot(env.origin))


def test_knowledge_partial_seams_are_refused_at_construction(env):
    binding = pub.PublisherBinding(
        worktree=str(env.clone),
        expected_origin=str(env.origin),
        default_branch=DEFAULT_BRANCH,
        publisher_identity=PUBLISHER_IDENTITY,
    )
    with pytest.raises(TypeError):
        make_publisher(
            binding,
            AuthoredProposalCompiler(expected_commit_of(env)),
            authorize,
            permission_stamp,
            qualify_publisher,
            InertPullRequestOwner(env.origin),
            authorize_knowledge="knowledge-authorizer-label",
        )


def test_knowledge_phase_started_cannot_begin_effects(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    stored = handle.events.operations[
        (AUTHORIZED_PRINCIPAL.subject, KNOWLEDGE_ACTION_FILE_ADD, request["request_id"])
    ]
    stored["metadata"]["phase"] = "STARTED"
    before = snapshot(env.clone), snapshot(env.origin)

    result = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "EFFECT_UNKNOWN"
    assert result["reason"] == "NO_EXISTING_PUBLICATION"
    assert handle.pr_owner.create_calls == 0
    assert before == (snapshot(env.clone), snapshot(env.origin))


def test_knowledge_retained_not_dispatched_is_terminal(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    stored = handle.events.operations[
        (AUTHORIZED_PRINCIPAL.subject, KNOWLEDGE_ACTION_FILE_ADD, request["request_id"])
    ]
    stored["metadata"]["phase"] = "NOT_DISPATCHED"

    published = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )
    reconciled = handle.publisher.reconcile_knowledge(
        knowledge_lookup(request), AUTHORIZED_PRINCIPAL
    )

    assert_closed_knowledge_result(published)
    assert published["state"] == "NOT_DISPATCHED"
    assert_closed_knowledge_result(reconciled)
    assert reconciled["state"] == "NOT_DISPATCHED"
    assert handle.pr_owner.create_calls == 0


def test_knowledge_retained_source_published_requires_matching_proof(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    stored = handle.events.operations[
        (AUTHORIZED_PRINCIPAL.subject, KNOWLEDGE_ACTION_FILE_ADD, request["request_id"])
    ]
    # Source-observed phase without matching publication proof: not claimable.
    stored["metadata"]["phase"] = "SOURCE_PUBLISHED"
    result = handle.publisher.reconcile_knowledge(
        knowledge_lookup(request), AUTHORIZED_PRINCIPAL
    )
    assert_closed_knowledge_result(result)
    assert result["state"] == "EFFECT_UNKNOWN"
    assert result["reason"] == "NO_EXISTING_PUBLICATION"
    assert result["source"] is None


def test_knowledge_existing_branch_publish_is_readonly(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    first = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )
    assert first["state"] == "PROPOSAL_PUBLISHED"
    branch = knowledge_branch(request)
    branch_commit = rev_parse(env.origin, "refs/heads/" + branch)
    receipt_number = first["proposal"]["number"]
    create_calls = handle.pr_owner.create_calls
    before = snapshot(env.clone), snapshot(env.origin)

    second = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )

    assert_closed_knowledge_result(second)
    assert second["state"] == "PROPOSAL_PUBLISHED"
    assert second["proposal"]["number"] == receipt_number
    assert rev_parse(env.origin, "refs/heads/" + branch) == branch_commit
    assert handle.pr_owner.create_calls == create_calls, "no second PR"
    assert before == (snapshot(env.clone), snapshot(env.origin))


def test_knowledge_pr_refusal_is_not_retried(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    handle.pr_owner.create_error = pub.PrOwnerRefused("fixture refusal")
    first = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )
    assert first["state"] == "PREPARED" and first["reason"] == "PR_CREATION_REFUSED"
    handle.pr_owner.create_error = None
    before = snapshot(env.clone), snapshot(env.origin)

    again = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )

    assert_closed_knowledge_result(again)
    assert again["state"] == "PREPARED"
    assert handle.pr_owner.create_calls == 1
    assert before == (snapshot(env.clone), snapshot(env.origin))
    reconciled = handle.publisher.reconcile_knowledge(
        knowledge_lookup(request), AUTHORIZED_PRINCIPAL
    )
    assert reconciled["state"] == "PREPARED"
    assert reconciled["reason"] == "REMOTE_BRANCH_WITHOUT_PR"


def test_knowledge_unknown_pr_outcome_is_effect_unknown_then_reconciled(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    handle.pr_owner.create_error = pub.PrOwnerUnknownOutcome("fixture: gh 5xx")
    result = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )
    assert_closed_knowledge_result(result)
    assert result["state"] == "EFFECT_UNKNOWN"
    assert result["reason"] == "PR_CREATION_UNKNOWN"
    branch = knowledge_branch(request)
    assert rev_parse(env.origin, "refs/heads/" + branch) is not None
    # The write landed upstream and the PR exists after all: read-only discovery.
    head = rev_parse(env.origin, "refs/heads/" + branch)
    handle.pr_owner.pull_requests[branch] = {
        "number": 402,
        "url": "https://github.com/%s/pull/402" % REPOSITORY,
        "head_commit": head,
        "head_branch": branch,
    }
    create_calls = handle.pr_owner.create_calls
    before = snapshot(env.clone), snapshot(env.origin)

    reconciled = handle.publisher.reconcile_knowledge(
        knowledge_lookup(request), AUTHORIZED_PRINCIPAL
    )

    assert_closed_knowledge_result(reconciled)
    assert reconciled["state"] == "PROPOSAL_PUBLISHED"
    assert reconciled["proposal"]["number"] == 402
    assert handle.pr_owner.create_calls == create_calls, "reconcile never creates"
    assert before == (snapshot(env.clone), snapshot(env.origin))


def test_knowledge_body_free_reconcile_after_compilers_absent(env):
    """Reconcile works from the body-free selection only and never recompiles."""
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    published = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )
    assert published["state"] == "PROPOSAL_PUBLISHED"

    def raising_compiler(request_arg):
        raise AssertionError("reconcile must never call the CREATE compiler")

    binding = handle.binding
    publisher = make_publisher(
        binding,
        raising_compiler,
        authorize,
        permission_stamp,
        qualify_publisher,
        handle.pr_owner,
        authorize_knowledge=handle.events.authorize_knowledge,
        knowledge_permission_stamp=handle.events.knowledge_permission_stamp,
        load_original_operation=handle.events.load_original_operation,
        validate_original_claim=handle.events.validate_original_claim,
    )

    reconciled = publisher.reconcile_knowledge(
        knowledge_lookup(request), AUTHORIZED_PRINCIPAL
    )

    assert_closed_knowledge_result(reconciled)
    assert reconciled["state"] == "PROPOSAL_PUBLISHED"
    assert reconciled["selection"] == knowledge_lookup(request)
    assert reconciled["source"] is None
    assert handle.compiler.requests_seen == []


def test_knowledge_reconcile_without_retained_metadata_is_unknown(env):
    base = seed_preimages(env, {CANONICAL_PATH: WORKSTREAM_TEXT})
    request = make_file_add_request(base)
    handle = build_knowledge_publisher(env)
    before = snapshot(env.clone), snapshot(env.origin)

    result = handle.publisher.reconcile_knowledge(
        knowledge_lookup(request), AUTHORIZED_PRINCIPAL
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "EFFECT_UNKNOWN"
    assert result["reason"] == "NO_EXISTING_PUBLICATION"
    assert result["source"] is None and result["proposal"] is None
    assert handle.pr_owner.create_calls == 0
    assert before == (snapshot(env.clone), snapshot(env.origin))


def test_knowledge_retained_source_proof_survives_later_default_edit(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    published = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )
    assert published["state"] == "PROPOSAL_PUBLISHED"
    branch = knowledge_branch(request)
    integrator = env.tmp_path / "integrator"
    git(env.tmp_path, "clone", str(env.origin), str(integrator))
    git(integrator, "fetch", "origin", branch)
    git(integrator, "checkout", "-q", DEFAULT_BRANCH)
    git(integrator, "merge", "--no-ff", "--no-edit", "FETCH_HEAD")
    git(integrator, "push", "origin", DEFAULT_BRANCH)
    merged_commit = rev_parse(env.origin, "refs/heads/" + DEFAULT_BRANCH)
    # Owner-retained source-observed Event publication proof for the original.
    stored = handle.events.operations[
        (AUTHORIZED_PRINCIPAL.subject, KNOWLEDGE_ACTION_FILE_ADD, request["request_id"])
    ]
    stored["metadata"]["phase"] = "SOURCE_PUBLISHED"
    stored["metadata"]["publication"] = {
        "repository": REPOSITORY,
        "commit": merged_commit,
        "postimages": [
            {"path": image["path"], "content_sha256": image["content_sha256"]}
            for image in recipe["postimages"]
        ],
    }
    # A later default edit changes the current upstream bytes away from the
    # canonical postimages; the retained proof must survive it.
    (integrator / CANONICAL_PATH).write_text(
        "# later unrelated default edit\n", encoding="utf-8"
    )
    git(integrator, "add", CANONICAL_PATH)
    git(integrator, "commit", "-m", "later default edit")
    git(integrator, "push", "origin", DEFAULT_BRANCH)
    assert rev_parse(env.origin, "refs/heads/" + DEFAULT_BRANCH) != merged_commit
    before_clone_refs = refs(env.clone)
    before_origin = snapshot(env.origin)

    result = handle.publisher.reconcile_knowledge(
        knowledge_lookup(request), AUTHORIZED_PRINCIPAL
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "SOURCE_PUBLISHED"
    assert result["source"]["commit"] == merged_commit
    assert handle.pr_owner.create_calls == 1
    assert refs(env.clone) == before_clone_refs
    assert_unchanged(before_origin, env.origin)


def test_knowledge_no_proof_and_diverged_default_is_unknown(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    base = request["source_commit"]
    # The default moves on and never carries the canonical postimages; the
    # retained metadata has no publication proof and nothing was dispatched.
    seed_preimages(env, {"agentos/notes/other.txt": "other\n"})
    before = snapshot(env.clone), snapshot(env.origin)

    result = handle.publisher.reconcile_knowledge(
        knowledge_lookup(request), AUTHORIZED_PRINCIPAL
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "EFFECT_UNKNOWN"
    assert result["reason"] == "STALE_EXPECTED_COMMIT"
    assert result["retryable"] is False
    assert result["source"] is None and result["proposal"] is None
    assert handle.pr_owner.create_calls == 0
    assert before == (snapshot(env.clone), snapshot(env.origin))
    assert rev_parse(env.origin, "refs/heads/" + DEFAULT_BRANCH) != base


# --------------------------------------------------------------------------- #
# Knowledge revocation windows and grant rotation
# --------------------------------------------------------------------------- #


def test_knowledge_revocation_before_effects_writes_nothing(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)

    def denied(principal, action, work_ref):
        return False

    binding = handle.binding
    publisher = make_publisher(
        binding,
        handle.compiler,
        authorize,
        permission_stamp,
        qualify_publisher,
        handle.pr_owner,
        authorize_knowledge=denied,
        knowledge_permission_stamp=handle.events.knowledge_permission_stamp,
        load_original_operation=handle.events.load_original_operation,
        validate_original_claim=handle.events.validate_original_claim,
    )
    before = snapshot(env.clone), snapshot(env.origin)

    result = publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "NOT_DISPATCHED"
    assert result["reason"] == "UNAUTHORIZED"
    assert handle.pr_owner.create_calls == 0
    assert before == (snapshot(env.clone), snapshot(env.origin))


def test_knowledge_revocation_after_write_is_effect_unknown(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    branch = knowledge_branch(request)

    def gate(principal, action, work_ref):
        if handle.events.authorize_knowledge(principal, action, work_ref) is not True:
            return False
        return rev_parse(env.origin, "refs/heads/" + branch) is None

    binding = handle.binding
    publisher = make_publisher(
        binding,
        handle.compiler,
        authorize,
        permission_stamp,
        qualify_publisher,
        handle.pr_owner,
        authorize_knowledge=gate,
        knowledge_permission_stamp=handle.events.knowledge_permission_stamp,
        load_original_operation=handle.events.load_original_operation,
        validate_original_claim=handle.events.validate_original_claim,
    )

    result = publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "EFFECT_UNKNOWN"
    assert result["reason"] == "AUTHORIZATION_REVOKED"
    assert rev_parse(env.origin, "refs/heads/" + branch) is not None
    assert handle.pr_owner.create_calls == 0, "no PR after revocation"


def test_knowledge_distinct_grants_publish_independently(env):
    base = seed_preimages(env, {CANONICAL_PATH: WORKSTREAM_TEXT})
    owner = Principal("mmos-workspace-project-owner@fixture")
    second = Principal("mmos-second-workspace-owner@fixture")
    handle = build_knowledge_publisher(env)
    request_a = make_file_add_request(base)
    request_b = make_file_add_request(
        base, request_id="mmos-project-file-add-" + "4" * 40, content="# Other file\n"
    )
    recipe_a = build_file_add_recipe(request_a, owner)
    recipe_b = build_file_add_recipe(request_b, second, file_content="# Other file\n")
    claim_a = handle.events.record(owner, request_a, recipe_a)
    claim_b = handle.events.record(second, request_b, recipe_b)

    result_a = handle.publisher.publish_knowledge(
        request_a, recipe_a, owner, claim=claim_a
    )
    result_b = handle.publisher.publish_knowledge(
        request_b, recipe_b, second, claim=claim_b
    )

    assert_closed_knowledge_result(result_a)
    assert_closed_knowledge_result(result_b)
    assert result_a["state"] == "PROPOSAL_PUBLISHED"
    assert result_b["state"] == "PROPOSAL_PUBLISHED"
    assert knowledge_branch(request_a, owner) != knowledge_branch(request_b, second)
    assert len(handle.pr_owner.pull_requests) == 2
    assert handle.pr_owner.create_calls == 2


# --------------------------------------------------------------------------- #
# Knowledge Git environment and caller-state preservation
# --------------------------------------------------------------------------- #


def test_knowledge_remote_branch_conflict_is_not_overwritten(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    branch = knowledge_branch(request)
    base = request["source_commit"]
    blob = git(env.clone, "hash-object", "-w", "--stdin", stdin=b"foreign payload\n").strip()
    tree = git(env.clone, "mktree", stdin="100644 blob %s\tcollision.txt\n" % blob).strip()
    collision = git(env.clone, "commit-tree", tree, "-p", base, "-m", "foreign").strip()
    git(env.clone, "push", "origin", "%s:refs/heads/%s" % (collision, branch))
    before = snapshot(env.origin)

    result = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "CONFLICT"
    assert result["reason"] == "REMOTE_BRANCH_CONFLICT"
    assert rev_parse(env.origin, "refs/heads/" + branch) == collision
    assert handle.pr_owner.create_calls == 0
    assert before == snapshot(env.origin)


def test_knowledge_distinct_pushurl_refuses_before_writes(env, tmp_path):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    foreign = tmp_path / "other.git"
    git(tmp_path, "init", "--bare", str(foreign))
    git(env.clone, "remote", "set-url", "--push", "origin", str(foreign))
    before = snapshot(env.clone), snapshot(env.origin), snapshot(foreign)

    result = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "NOT_DISPATCHED"
    assert result["reason"] == "ORIGIN_MISMATCH"
    assert before == (snapshot(env.clone), snapshot(env.origin), snapshot(foreign))


def test_knowledge_ambient_git_env_cannot_redirect(env, tmp_path, monkeypatch):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    foreign = tmp_path / "foreign.git"
    git(tmp_path, "init", "--bare", str(foreign))
    before = snapshot(foreign)
    with monkeypatch.context() as hostile:
        hostile.setenv("GIT_DIR", str(foreign))
        hostile.setenv("GIT_INDEX_FILE", str(tmp_path / "hostile-index"))
        result = handle.publisher.publish_knowledge(
            request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
        )
    assert_closed_knowledge_result(result)
    assert result["state"] == "PROPOSAL_PUBLISHED"
    assert not (tmp_path / "hostile-index").exists()
    assert before == snapshot(foreign)


def test_knowledge_caller_state_preserved(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    (env.clone / "notes").mkdir()
    (env.clone / "notes" / "scratch.txt").write_text("dirty\n", encoding="utf-8")
    (env.clone / "staged.txt").write_text("staged\n", encoding="utf-8")
    git(env.clone, "add", "staged.txt")
    head_before = rev_parse(env.clone, "HEAD")
    status_before = git(env.clone, "status", "--porcelain")
    staged_before = git(env.clone, "diff", "--cached", "--name-only")

    result = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "PROPOSAL_PUBLISHED"
    assert rev_parse(env.clone, "HEAD") == head_before
    assert git(env.clone, "status", "--porcelain") == status_before
    assert git(env.clone, "diff", "--cached", "--name-only") == staged_before
    media_path = recipe["postimages"][0]["path"]
    assert not (env.clone / media_path).exists(), "never writes worktree files"


def test_knowledge_result_exposes_no_sensitive_material(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)

    result = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )

    encoded = json.dumps(result)
    assert FILE_CONTENT not in encoded
    assert recipe["postimages"][1]["content_utf8"] not in encoded
    assert "claim-" not in encoded
    assert str(env.clone) not in encoded
    assert PUBLISHER_IDENTITY not in encoded
    assert PERMISSION_BINDING_DIGEST not in encoded
    assert "token" not in encoded.lower()
    assert set(result.keys()) == KNOWLEDGE_RESULT_KEYS
    assert result["selection"] == knowledge_lookup(request)


def test_knowledge_reconcile_result_carries_no_bodies(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    handle.pr_owner.create_error = pub.PrOwnerRefused("fixture refusal")
    handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )
    handle.pr_owner.create_error = None

    result = handle.publisher.reconcile_knowledge(
        knowledge_lookup(request), AUTHORIZED_PRINCIPAL
    )

    encoded = json.dumps(result)
    assert FILE_CONTENT not in encoded
    assert recipe["postimages"][1]["content_utf8"] not in encoded
    assert set(result.keys()) == KNOWLEDGE_RESULT_KEYS
    assert result["state"] == "PREPARED"


def test_knowledge_globals_unchanged_by_publication(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )
    handle.publisher.reconcile_knowledge(
        knowledge_lookup(request), AUTHORIZED_PRINCIPAL
    )
    # No runtime ledger in the module: globals are exactly the import-time set.
    assert frozenset(vars(pub).keys()) == MODULE_GLOBALS_AT_IMPORT


def test_knowledge_qualifier_refusal_denies_before_writes(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)

    def refused_qualifier(binding):
        return False

    binding = handle.binding
    publisher = make_publisher(
        binding,
        handle.compiler,
        authorize,
        permission_stamp,
        refused_qualifier,
        handle.pr_owner,
        authorize_knowledge=handle.events.authorize_knowledge,
        knowledge_permission_stamp=handle.events.knowledge_permission_stamp,
        load_original_operation=handle.events.load_original_operation,
        validate_original_claim=handle.events.validate_original_claim,
    )
    before = snapshot(env.clone), snapshot(env.origin)

    result = publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "NOT_DISPATCHED"
    assert result["reason"] == "QUALIFIER_REFUSED"
    assert before == (snapshot(env.clone), snapshot(env.origin))
    assert handle.pr_owner.create_calls == 0


def test_knowledge_seam_identity_change_denies_before_writes(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    before = snapshot(env.clone), snapshot(env.origin)
    # The captured knowledge authorizer reference is swapped for a different
    # object: captured identity drift must refuse before any effect.
    handle.publisher._authorize_knowledge = lambda principal, action, work_ref: True

    result = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )

    assert_closed_knowledge_result(result)
    assert result["state"] == "NOT_DISPATCHED"
    assert result["reason"] == "SEAM_IDENTITY_CHANGED"
    assert before == (snapshot(env.clone), snapshot(env.origin))
    assert handle.pr_owner.create_calls == 0


def test_knowledge_changed_action_or_scope_conflicts(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    key = (AUTHORIZED_PRINCIPAL.subject, KNOWLEDGE_ACTION_FILE_ADD, request["request_id"])
    before = snapshot(env.clone), snapshot(env.origin)

    stored = handle.events.operations[key]
    stored["metadata"]["identity"]["action"] = KNOWLEDGE_ACTION_PREFERENCE
    result = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )
    assert_closed_knowledge_result(result)
    assert result["state"] == "CONFLICT"
    assert result["reason"] == "OPERATION_CONFLICT"

    stored["metadata"]["identity"]["action"] = KNOWLEDGE_ACTION_FILE_ADD
    stored["metadata"]["identity"]["principal_scope"] = "f" * 64
    result = handle.publisher.publish_knowledge(
        request, recipe, AUTHORIZED_PRINCIPAL, claim=claim
    )
    assert_closed_knowledge_result(result)
    assert result["state"] == "CONFLICT"
    assert result["reason"] == "OPERATION_CONFLICT"

    assert before == (snapshot(env.clone), snapshot(env.origin))
    assert handle.pr_owner.create_calls == 0


def test_knowledge_original_stamp_must_match_current_distinct_action_grant(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    calls = []
    def current_stamp(principal, action, work_ref):
        calls.append((principal, action, work_ref))
        return 'f' * 64
    publisher = build_knowledge_publisher(
        env, events=handle.events, knowledge_permission_stamp=current_stamp,
    ).publisher
    before = snapshot(env.clone), snapshot(env.origin)
    result = publisher.publish_knowledge(request, recipe, AUTHORIZED_PRINCIPAL, claim=claim)
    assert result['state'] == 'NOT_DISPATCHED'
    assert result['reason'] == 'AUTHORIZATION_REVOKED'
    assert calls == [(AUTHORIZED_PRINCIPAL, KNOWLEDGE_ACTION_FILE_ADD, WORK_REF)]
    assert before == (snapshot(env.clone), snapshot(env.origin))


def test_knowledge_current_stamp_change_after_push_keeps_unknown(env):
    handle, request, recipe, claim = knowledge_file_add_setup(env)
    branch = knowledge_branch(request)
    def current_stamp(principal, action, work_ref):
        return ('f' * 64 if rev_parse(env.origin, 'refs/heads/' + branch) else
                knowledge_stamp_for(principal, action, work_ref))
    joined = build_knowledge_publisher(env, events=handle.events, knowledge_permission_stamp=current_stamp)
    result = joined.publisher.publish_knowledge(request, recipe, AUTHORIZED_PRINCIPAL, claim=claim)
    assert result['state'] == 'EFFECT_UNKNOWN'
    assert result['reason'] == 'AUTHORIZATION_REVOKED'
    assert rev_parse(env.origin, 'refs/heads/' + branch)
    assert joined.pr_owner.create_calls == 0


@pytest.mark.parametrize('mode', ['file', 'preference-new', 'preference-edit'])
def test_actual_macro_knowledge_recipe_publishes_exact_atomic_postimages(env, mode):
    # Actual canonical compiler and records; only Git and PR effects use local fixtures.
    from tests.knowledge_recipe_test_support import (
        HAS_OWNER_RECIPES, load_recipes, canonical_workstream,
    )
    if not HAS_OWNER_RECIPES:
        pytest.skip('Actual MM_TEST_MACRO_OWNER_ROOT recipe source not supplied')
    recipes = load_recipes()
    ws = canonical_workstream().replace('ALPHA', 'DEMO')
    actor = 'workspace:' + scope_of(AUTHORIZED_PRINCIPAL)
    decision = None
    if mode == 'preference-edit':
        seed_request = make_preference_request('a' * 40, base_revision=sha_hex(ws))
        seed_recipe = recipes.build_project_preference_set(
            seed_request, actor_ref=actor,
            permission_binding_digest=knowledge_stamp_for(AUTHORIZED_PRINCIPAL, KNOWLEDGE_ACTION_PREFERENCE, WORK_REF),
            captured_commit='a' * 40, workstream_text=ws,
            decision_text=None, decision_date='2026-02-01',
        )
        images = {image['path']: image['content_utf8'] for image in seed_recipe['postimages']}
        ws = images[CANONICAL_PATH]
        decision_path = next(path for path in images if path != CANONICAL_PATH)
        decision = images[decision_path]
    files = {CANONICAL_PATH: ws}
    if decision is not None:
        files[decision_path] = decision
    base = seed_preimages(env, files)
    if mode == 'file':
        request = make_file_add_request(base, base_revision=sha_hex(ws))
        recipe = recipes.build_project_file_add(
            request, actor_ref=actor,
            permission_binding_digest=knowledge_stamp_for(AUTHORIZED_PRINCIPAL, KNOWLEDGE_ACTION_FILE_ADD, WORK_REF),
            captured_commit=base, workstream_text=ws,
        )
    else:
        request = make_preference_request(base, value='Literal 中文\nsecond line',
            request_id='mmos-project-preference-set-' + '9' * 40,
            base_revision=sha_hex(ws), expected_preference_revision=sha_hex(decision) if decision else None)
        recipe = recipes.build_project_preference_set(
            request, actor_ref=actor,
            permission_binding_digest=knowledge_stamp_for(AUTHORIZED_PRINCIPAL, KNOWLEDGE_ACTION_PREFERENCE, WORK_REF),
            captured_commit=base, workstream_text=ws,
            decision_text=decision, decision_date='2026-02-02',
        )
    handle = build_knowledge_publisher(env)
    claim = handle.events.record(AUTHORIZED_PRINCIPAL, request, recipe)
    result = handle.publisher.publish_knowledge(request, recipe, AUTHORIZED_PRINCIPAL, claim=claim)
    assert result['state'] == 'PROPOSAL_PUBLISHED', json.dumps(result,ensure_ascii=False)
    commit = result['proposal']['head_commit']
    assert git(env.clone, 'rev-list', '--parents', '-n', '1', commit).split() == [commit, base]
    for image in recipe['postimages']:
        body = git(env.clone, 'cat-file', 'blob', commit + ':' + image['path'])
        assert body == image['content_utf8']
        assert sha_hex(body) == image['content_sha256']
    changed = git(env.clone, 'diff-tree', '-r', '--no-commit-id', '--name-only', commit).splitlines()
    assert len(changed) == (1 if mode == 'preference-edit' else 2)
    before = snapshot(env.origin)
    status = handle.publisher.reconcile_knowledge(knowledge_lookup(request), AUTHORIZED_PRINCIPAL)
    assert status['state'] == 'PROPOSAL_PUBLISHED'
    assert handle.pr_owner.create_calls == 1
    assert before == snapshot(env.origin)
