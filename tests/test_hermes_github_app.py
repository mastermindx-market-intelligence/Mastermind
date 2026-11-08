"""Host-bound GitHub App authoring, real HTTPX transport, no live credentials."""
import asyncio
import json

import httpx
import pytest

from integrations.github_review_app_token import (
    AUTHORING_PERMISSIONS, GitHubAppInstallationTokens,
    GitHubAppTokenUnavailable,
)
from integrations.hermes_github_app import (
    SCHEMA, HermesGitHubApp, HostGitHubSession,
    GitHubBotRefused, GitHubBotEffectUnknown,
)
from integrations.hermes_github_native import (
    HostHermesGitHubBinding, native_handler,
)

BASE = "a" * 40
TREE = "b" * 40
NEXT_TREE = "c" * 40
COMMIT = "d" * 40
REPO = "example/repo"
BRANCH = "hermes/work-001"


class FakeGitHub:
    def __init__(self):
        self.head = None
        self.prs = []
        self.comments = []
        self.writes = []
        self.fail_post_comment = False
        self.revoke = None
        self.audit = None

    def handle(self, req):
        assert req.url.host == "api.github.com"
        assert req.headers["authorization"] == "Bearer never-expose-this-token"
        assert req.headers["accept-encoding"] == "identity"
        path = req.url.path
        method = req.method
        if method != "GET":
            self.writes.append((method, path))
        if method == "GET" and path == "/repos/example/repo/git/ref/heads/master":
            return httpx.Response(200, json={"object": {"sha": BASE}})
        if method == "GET" and path == "/repos/example/repo/git/ref/heads/" + BRANCH:
            if self.head is None:
                return httpx.Response(404, json={"message": "missing"})
            return httpx.Response(200, json={"object": {"sha": self.head}})
        if method == "POST" and path == "/repos/example/repo/git/refs":
            data = json.loads(req.content)
            assert data == {"ref": "refs/heads/" + BRANCH, "sha": BASE}
            self.head = BASE
            return httpx.Response(201, json={
                "ref": "refs/heads/" + BRANCH,
                "object": {"sha": BASE},
            })
        if method == "GET" and path == "/repos/example/repo/git/commits/" + BASE:
            return httpx.Response(200, json={"tree": {"sha": TREE}})
        if method == "POST" and path == "/repos/example/repo/git/trees":
            data = json.loads(req.content)
            assert data["base_tree"] == TREE
            assert data["tree"][0]["mode"] == "100644"
            assert data["tree"][0]["path"] == "docs/hermes/test.txt"
            return httpx.Response(201, json={"sha": NEXT_TREE})
        if method == "POST" and path == "/repos/example/repo/git/commits":
            data = json.loads(req.content)
            assert data["tree"] == NEXT_TREE and data["parents"] == [BASE]
            assert self.audit in data["message"]
            return httpx.Response(201, json={"sha": COMMIT})
        if method == "PATCH" and path == "/repos/example/repo/git/refs/heads/" + BRANCH:
            data = json.loads(req.content)
            assert data == {"sha": COMMIT, "force": False}
            self.head = COMMIT
            if self.revoke:
                self.revoke()
            return httpx.Response(200, json={"object": {"sha": COMMIT}})
        if method == "GET" and path == "/repos/example/repo/pulls":
            return httpx.Response(200, json=self.prs)
        if method == "POST" and path == "/repos/example/repo/pulls":
            data = json.loads(req.content)
            assert data["head"] == BRANCH and data["base"] == "master"
            assert self.audit in data["body"]
            pr = {
                "number": 42, "html_url": "https://github.com/example/repo/pull/42",
                "head": {"sha": self.head, "ref": BRANCH,
                         "repo": {"full_name": REPO}},
                "base": {"ref": "master"},
                "body": data["body"],
            }
            self.prs.append(pr)
            return httpx.Response(201, json=pr)
        if method == "GET" and path == "/repos/example/repo/pulls/42":
            return httpx.Response(200, json=self.prs[0]) if self.prs else httpx.Response(404)
        if method == "GET" and path == "/repos/example/repo/pulls/99":
            return httpx.Response(404)
        if method == "GET" and path == "/repos/example/repo/issues/42/comments":
            return httpx.Response(200, json=self.comments)
        if method == "POST" and path == "/repos/example/repo/issues/42/comments":
            data = json.loads(req.content)
            assert self.audit in data["body"]
            comment = {
                "id": 777, "html_url": "https://github.com/example/repo/issues/42#comment-777",
                "body": data["body"],
            }
            self.comments.append(comment)
            if self.fail_post_comment:
                raise httpx.ReadTimeout("lost response after GitHub write")
            return httpx.Response(201, json=comment)
        return httpx.Response(404, json={"unexpected": [method, path]})


def make(fake=None, *, authorized_paths=("docs/hermes/",), allowed_issues=frozenset(),
         role="engineering", guard=None, branch=BRANCH):
    fake = fake or FakeGitHub()
    issuer = GitHubAppInstallationTokens(
        app_id=123, installation_id=4321, repository=REPO,
        private_key_source=lambda: b"not-used-in-mock",
        permissions=AUTHORING_PERMISSIONS,
    )
    issuer.token_for_installation = lambda *, installation_id: (
        "never-expose-this-token" if installation_id == 4321 else "wrong"
    )
    state = {"current": True}
    guard = guard or (lambda: state["current"])
    binding = HostGitHubSession(
        profile_id="engineering", role=role, session_id="session-123",
        operation_id="work-001", repository=REPO,
        branch=branch, base_branch="master", base_sha=BASE,
        installation_id=4321, allowed_path_prefixes=authorized_paths,
        allowed_issue_numbers=allowed_issues, token_source=issuer,
        currentness_guard=guard,
    )
    fake.audit = binding.audit_marker
    app = HermesGitHubApp(binding, client=httpx.Client(
        transport=httpx.MockTransport(fake.handle),
    ))
    return app, fake, state


def test_one_shared_app_actor_can_prove_original_bot_session_and_author():
    app, fake, _ = make()
    assert app.perform({"action": "branch_create"}) == {
        "schema": SCHEMA, "state": "CREATED", "head": BASE,
    }
    assert app.perform({"action": "branch_create"})["state"] == "EXISTS"
    commit = app.perform({
        "action": "file_commit", "expected_head": BASE,
        "path": "docs/hermes/test.txt", "content": "verified\n",
        "message": "docs: Hermes bot can commit",
    })
    assert commit["head"] == COMMIT
    pr = app.perform({
        "action": "pr_create", "expected_head": COMMIT,
        "title": "Hermes integrated App canary", "body": "Scoped PR body",
    })
    assert pr["number"] == 42
    comment = app.perform({
        "action": "comment_create", "issue_number": 42,
        "request_id": "reply-0001", "body": "Canary reply",
    })
    assert comment["id"] == 777
    assert app.perform({
        "action": "pr_create", "expected_head": COMMIT,
        "title": "Hermes integrated App canary", "body": "Scoped PR body",
    })["state"] == "EXISTS"
    assert app.perform({
        "action": "comment_create", "issue_number": 42,
        "request_id": "reply-0001", "body": "Canary reply",
    })["state"] == "EXISTS"
    assert fake.audit.startswith("mmx-hermes-app role=engineering operation=work-001")
    assert "session-123" not in fake.audit
    assert fake.writes == [
        ("POST", "/repos/example/repo/git/refs"),
        ("POST", "/repos/example/repo/git/trees"),
        ("POST", "/repos/example/repo/git/commits"),
        ("PATCH", "/repos/example/repo/git/refs/heads/" + BRANCH),
        ("POST", "/repos/example/repo/pulls"),
        ("POST", "/repos/example/repo/issues/42/comments"),
    ]


@pytest.mark.parametrize("bad", [
    {"action": "status", "repository": "other/repo"},
    {"action": "comment_create", "issue_number": 42, "request_id": "x"},
    {"action": "file_commit", "expected_head": BASE,
     "path": "../secrets", "content": "x", "message": "changed"},
    {"action": "file_commit", "expected_head": BASE,
     "path": "docs/hermes/../secrets", "content": "x", "message": "changed"},
])
def test_model_cannot_select_target_or_escape_authorized_scope(bad):
    app, fake, _ = make()
    with pytest.raises(GitHubBotRefused):
        app.perform(bad)
    assert fake.writes == []


def test_branch_head_change_refuses_without_mutating():
    app, fake, _ = make()
    app.create_branch()
    fake.writes.clear()
    with pytest.raises(GitHubBotRefused, match="HEAD_CHANGED"):
        app.commit_file(
            expected_head=COMMIT, path="docs/hermes/test.txt",
            content="x", message="docs: changed",
        )
    assert fake.writes == []


def test_app_scoping_and_different_bot_role_are_independent():
    app, fake, state = make()
    app.create_branch()
    state["current"] = False
    fake.writes.clear()
    with pytest.raises(GitHubBotRefused, match="REVOKED"):
        app.commit_file(
            expected_head=BASE, path="docs/hermes/test.txt",
            content="x", message="docs: changed",
        )
    assert fake.writes == []
    with pytest.raises(GitHubBotRefused):
        make(role="wrong role")
    with pytest.raises(GitHubBotRefused):
        make(authorized_paths=())


def test_comment_unknown_effect_preserves_original_and_readback_can_reconcile():
    app, fake, _ = make()
    app.create_branch()
    app.create_pr(expected_head=BASE, title="Canary issue", body="Body")
    fake.fail_post_comment = True
    with pytest.raises(GitHubBotEffectUnknown):
        app.create_comment(issue_number=42, request_id="lost-response-1", body="Hello")
    # The client made exactly one send, and the comment really exists on GitHub.
    assert len(fake.comments) == 1
    assert app.find_comment(issue_number=42, request_id="lost-response-1")["id"] == 777


def test_revocation_during_write_is_unknown_not_refused():
    app, fake, state = make()
    app.create_branch()
    fake.revoke = lambda: state.update(current=False)
    with pytest.raises(GitHubBotEffectUnknown, match="GRANT_CHANGED"):
        app.commit_file(
            expected_head=BASE, path="docs/hermes/test.txt",
            content="x", message="docs: changed",
        )
    assert fake.head == COMMIT


def test_native_binding_rejects_forged_session_and_prevents_secret_projection():
    app, fake, _ = make()
    binding = HostHermesGitHubBinding(
        profile_id="engineering",
        resolve_client=lambda session: app if session == "session-123" else None,
        currentness_guard=lambda: True,
    )
    handler = native_handler(binding)
    result = json.loads(asyncio.run(handler(
        {"action": "status"}, session_id="session-123",
        task_id="session-123",
    )))
    assert result["state"] == "AVAILABLE"
    assert "never-expose-this-token" not in json.dumps(result)
    bad = json.loads(asyncio.run(handler(
        {"action": "branch_create"}, session_id="other",
    )))
    assert bad["state"] == "REFUSED"
    assert fake.writes == []


def test_legacy_review_profile_is_not_implicitly_authoring():
    old = GitHubAppInstallationTokens(
        app_id=1, installation_id=4321, repository=REPO,
        private_key_source=lambda: b"unused",
    )
    assert old._permissions == {"contents": "read", "pull_requests": "write"}
    with pytest.raises(GitHubAppTokenUnavailable, match="PROFILE_INVALID"):
        GitHubAppInstallationTokens(
            app_id=1, installation_id=4321, repository=REPO,
            private_key_source=lambda: b"unused",
            permissions={"administration": "write"},
        )
