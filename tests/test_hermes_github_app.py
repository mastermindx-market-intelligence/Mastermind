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
                "body": data["body"], "state": "open",
                "user": {"login": "mastermind-hermes-author[bot]"},
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
                "user": {"login": "mastermind-hermes-author[bot]"},
            }
            self.comments.append(comment)
            if self.fail_post_comment:
                raise httpx.ReadTimeout("lost response after GitHub write")
            return httpx.Response(201, json=comment)
        return httpx.Response(404, json={"unexpected": [method, path]})


def make(fake=None, *, authorized_paths=("docs/hermes/",), allowed_issues=frozenset(),
         role="engineering", guard=None, branch=BRANCH,
         profile_id="engineering"):
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
        profile_id=profile_id, role=role, session_id="session-123",
        operation_id="work-001", repository=REPO,
        branch=branch, base_branch="master", base_sha=BASE,
        installation_id=4321, app_bot_login="mastermind-hermes-author[bot]",
        allowed_path_prefixes=authorized_paths,
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

def test_unhashable_action_and_nonstring_host_fields_refuse_without_side_effect():
    app, fake, _ = make()
    with pytest.raises(GitHubBotRefused, match="ACTION_ARGUMENTS"):
        app.perform({"action": {}})
    assert fake.writes == []
    with pytest.raises(GitHubBotRefused, match="HOST_BINDING"):
        make(role=4)
    with pytest.raises(GitHubBotRefused, match="HOST_GRANT"):
        make(authorized_paths=(123,))


def test_prefix_not_directory_boundary_does_not_grant_sibling_files():
    app, fake, _ = make(authorized_paths=("docs/hermes",))
    assert app.binding.path_is_allowed("docs/hermes")
    assert not app.binding.path_is_allowed("docs/hermes_private/credentials.txt")
    assert not app.binding.path_is_allowed("docs/hermes/subtree.txt")
    assert fake.writes == []


def test_real_signed_authoring_issuer_scopes_token_and_rejects_extra_grants():
    from test_github_review_app_token import private_key, NOW
    import datetime

    key, pem = private_key()
    expiry = datetime.datetime.fromtimestamp(
        NOW + 1800, tz=datetime.timezone.utc,
    ).isoformat().replace("+00:00", "Z")
    observed = []
    def handler(request):
        payload = json.loads(request.content)
        observed.append(payload)
        assert payload == {
            "repositories": ["repo"],
            "permissions": {
                "contents": "write", "issues": "write",
                "pull_requests": "write",
            },
        }
        return httpx.Response(201, json={
            "token": "AUTHORING_TOKEN_NOT_FOR_TOOL_OUTPUT",
            "expires_at": expiry,
            "permissions": {**AUTHORING_PERMISSIONS, "metadata": "read"},
            "repositories": [{"full_name": REPO}],
        })

    source = GitHubAppInstallationTokens(
        app_id=123, installation_id=4321, repository=REPO,
        private_key_source=lambda: pem,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=lambda: NOW,
        permissions=AUTHORING_PERMISSIONS,
    )
    assert source.token_for_installation(installation_id=4321).startswith("AUTHORING_")
    assert source.token_for_installation(installation_id=4321).startswith("AUTHORING_")
    assert len(observed) == 1
    assert "AUTHORING_TOKEN_NOT_FOR_TOOL_OUTPUT" not in repr(source)

def test_actual_native_registration_owns_exact_tool_scope_when_donor_available(tmp_path, monkeypatch):
    """Optional upstream-native canary; never a claim of installed Hermes."""
    import os
    from pathlib import Path
    from integrations.hermes_github_native import (
        TOOL_NAME, register_native_tool,
    )
    root = os.environ.get("HERMES_LEADERSHIP_UPSTREAM")
    if not root:
        pytest.skip("native Hermes donor not provided")
    from integrations.hermes_harness.tests.test_native_tool_registration import _Upstream
    donor = Path(root)
    assert (donor / "hermes_cli/plugins.py").is_file()
    owner = _Upstream(donor)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    scope = tmp_path / "host-1"
    scope.mkdir()
    manager = owner.PluginManager(scope_key=str(scope))
    manifest = owner.PluginManifest(
        name="mastermind-github-app", version="1", source="project",
        path=str(scope), provides_tools=[TOOL_NAME], key="mastermind-github-app",
    )
    ctx = owner.PluginContext(manifest, manager)
    app, fake, _ = make(profile_id=ctx.profile_name)
    binding = HostHermesGitHubBinding(
        profile_id=ctx.profile_name,
        resolve_client=lambda session: app if session == "session-123" else None,
        currentness_guard=lambda: True,
    )
    lease = register_native_tool(ctx, binding, profile_id=ctx.profile_name)
    try:
        entry = owner.registry.snapshot_registration(TOOL_NAME, scope=str(scope))
        assert entry.handler is lease.handler and entry.is_async is True
        assert entry.schema["parameters"]["additionalProperties"] is False
        result = json.loads(asyncio.run(entry.handler(
            {"action": "status"}, session_id="session-123",
        )))
        assert result["state"] == "AVAILABLE"
        with pytest.raises(RuntimeError, match="GITHUB_NATIVE_COLLISION"):
            register_native_tool(ctx, binding, profile_id=ctx.profile_name)
    finally:
        lease.dispose()
    assert owner.registry.snapshot_registration(TOOL_NAME, scope=str(scope)) is None
    revoked = json.loads(asyncio.run(lease.handler(
        {"action": "status"}, session_id="session-123",
    )))
    assert revoked["state"] == "REFUSED"

def test_spoofed_pr_marker_from_human_never_becomes_app_identity():
    app, fake, _ = make()
    app.create_branch()
    fake.prs.append({
        "number": 91, "state": "open",
        "html_url": "https://github.com/example/repo/pull/91",
        "head": {"ref": BRANCH, "sha": BASE,
                 "repo": {"full_name": REPO}},
        "base": {"ref": "master"},
        "user": {"login": "some-human"},
        "body": "<!-- " + app.binding.audit_marker + " -->",
    })
    writes_before = len(fake.writes)
    with pytest.raises(GitHubBotRefused, match="PR_OWNED_BY_OTHER"):
        app.create_pr(expected_head=BASE, title="Impersonated PR", body="x")
    assert len(fake.writes) == writes_before


def test_spoofed_comment_marker_is_not_recovered_as_bot_comment():
    app, fake, _ = make()
    app.create_branch()
    app.create_pr(expected_head=BASE, title="Canary issue", body="Body")
    marker = "<!-- " + app.binding.audit_marker + " request=reply-forged -->"
    fake.comments.append({
        "id": 333, "body": marker,
        "user": {"login": "someone-else"},
        "html_url": "https://github.com/example/repo/issues/42#comment-333",
    })
    assert app.find_comment(issue_number=42, request_id="reply-forged") is None
    created = app.create_comment(
        issue_number=42, request_id="reply-forged", body="Actual bot response",
    )
    assert created["state"] == "CREATED" and created["id"] == 777


def test_missing_or_forged_author_bot_login_refuses_binding():
    app, fake, _ = make()
    with pytest.raises(GitHubBotRefused, match="HOST_BINDING_INVALID"):
        HostGitHubSession(
            profile_id="engineering", role="engineering",
            session_id="session-123", operation_id="work-001",
            repository=REPO, branch=BRANCH, base_branch="master", base_sha=BASE,
            installation_id=4321, app_bot_login="human-user",
            allowed_path_prefixes=("docs/hermes/",),
            allowed_issue_numbers=frozenset(),
            token_source=app.binding.token_source, currentness_guard=lambda: True,
        )
