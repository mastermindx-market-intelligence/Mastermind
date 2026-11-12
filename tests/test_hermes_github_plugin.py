"""Real pinned Hermes loader + mocked GitHub; never installed-host proof.

On the pre-#2285 base, the explicit dependency skip is expected. Qualification
must run with that exact source dependency AND HERMES_LEADERSHIP_UPSTREAM set
(as the incumbent native tests do); no dependency source is copied into git.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace

import httpx
import pytest

pytest.importorskip("integrations.hermes_github_native", reason="requires PR #2285 source")
from integrations.github_review_app_token import AUTHORING_PERMISSIONS, GitHubAppInstallationTokens
from integrations.hermes_github_app import HermesGitHubApp, HostGitHubSession
from integrations.hermes_github_native import HostHermesGitHubBinding, TOOL_SCHEMA
from integrations.hermes_github_plugin_host import bind_native_host, register_from_host

ROOT = Path(__file__).resolve().parents[1]
ACTOR = "fixture-author[bot]"
REPO = "example/repo"
NOW = 1800000000
BASE = "a" * 40


@pytest.fixture
def native(tmp_path, monkeypatch):
    donor = os.environ.get("HERMES_LEADERSHIP_UPSTREAM")
    if not donor:
        pytest.skip("pinned Hermes source not supplied; no native-loader proof")
    root = Path(donor)
    # Verify the executed loader against the incumbent source archive, not a stub.
    fixture = ROOT / "integrations/hermes_runtime/tests/fixtures/agentos_memory"
    provenance = json.loads((fixture / "provenance.json").read_text())
    for name in ("hermes_cli/plugins_loader.py", "hermes_cli/plugin_isolation.py"):
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == provenance["files"][name]["sha256"]
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "profile"))
    for name in ("HERMES_PROFILE", "HERMES_PROFILE_NAME", "HERMES_PLUGIN_HOST"):
        monkeypatch.delenv(name, raising=False)
    from hermes_cli.plugins import PluginContext, PluginManager
    from hermes_cli.plugins_manifest import parse_manifest_file
    from hermes_cli.plugins_loader import _plugin_home_scope
    from tools.registry import registry

    home = tmp_path / "profile"
    home.mkdir()
    # Explicit installed-operator selection; production code never changes it.
    (home / "config.yaml").write_text("plugins:\n  isolation: in_process\n")
    package = home / "plugins" / "mmx_github"
    shutil.copytree(ROOT / "integrations/hermes_github_plugin", package,
                    ignore=shutil.ignore_patterns("__pycache__"))
    manager = PluginManager(scope_key=str(home))
    manifest = parse_manifest_file(package / "plugin.yaml", package, "user", "")
    assert manifest is not None and manifest.provides_tools == []
    ctx = PluginContext(manifest, manager)
    with _plugin_home_scope(home):
        profile = ctx.profile_name
    result = SimpleNamespace(manager=manager, manifest=manifest, ctx=ctx,
                             package=package, home=home, registry=registry,
                             profile=profile, scope=_plugin_home_scope)
    yield result
    manager.unload()


@pytest.fixture
def app_host(native):
    calls, key_calls, comments = [], [], []
    clock = [NOW]
    live = {"host": True, "one": True, "two": True}
    actor = [ACTOR]

    def github(request):
        data = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, data))
        if request.url.path.endswith("/access_tokens"):
            assert data == {"repositories": ["repo"], "permissions": AUTHORING_PERMISSIONS}
            return httpx.Response(201, json={
                "token": "fixture-token", "expires_at": "2027-01-15T09:00:00Z",
                "permissions": AUTHORING_PERMISSIONS,
                "repositories": [{"full_name": REPO}],
            })
        assert request.headers["Authorization"] == "Bearer fixture-token"
        if request.url.path.endswith("/comments"):
            if request.method == "GET":
                return httpx.Response(200, json=comments)
            item = {"id": len(comments) + 1, "body": data["body"],
                    "user": {"login": actor[0]}, "html_url": "https://github.com/example/repo/issues/7"}
            comments.append(item)
            return httpx.Response(201, json=item)
        if "/git/ref/heads/" in request.url.path:
            return httpx.Response(200, json={"object": {"sha": BASE}})
        return httpx.Response(404, json={})

    # Ephemeral test-only RSA key. No key file or host credential is read.
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption())

    def read_test_key():
        key_calls.append(True)
        return key

    http = httpx.Client(transport=httpx.MockTransport(github))
    issuer = GitHubAppInstallationTokens(
        app_id=123, installation_id=456, repository=REPO,
        private_key_source=read_test_key, client=http, clock=lambda: clock[0],
        permissions=AUTHORING_PERMISSIONS)
    clients = {}
    for session in ("one", "two"):
        grant = HostGitHubSession(
            profile_id=native.profile, role="engineering", session_id=session,
            operation_id="operation-" + session, repository=REPO,
            branch="hermes/" + session, base_branch="master", base_sha=BASE,
            installation_id=456, app_bot_login=ACTOR,
            allowed_path_prefixes=("docs/",), allowed_issue_numbers=frozenset({7}),
            token_source=issuer,
            currentness_guard=lambda session=session: live[session] and clock[0] < NOW + 120)
        clients[session] = HermesGitHubApp(grant, client=http)
    binding = HostHermesGitHubBinding(
        profile_id=native.profile, resolve_client=clients.get,
        currentness_guard=lambda: live["host"])
    slot = bind_native_host(native.manager, binding=binding, issuer=issuer,
                            app_bot_login=ACTOR, package_path=native.package)
    yield SimpleNamespace(**vars(native), calls=calls, key_calls=key_calls,
                          comments=comments, clients=clients, issuer=issuer,
                          binding=binding, slot=slot, live=live, clock=clock, actor=actor)
    slot.close()
    http.close()


def load(host):
    host.manager._load_plugin(host.manifest)
    loaded = host.manager._plugins["mmx_github"]
    assert loaded.enabled, loaded.error
    entry = host.registry.snapshot_registration("mmx_github", scope=str(host.home))
    assert entry is host.slot.registration.entry
    return entry


def invoke(host, entry, arguments=None, session="one"):
    with host.scope(host.home):
        return json.loads(asyncio.run(entry.handler(
            arguments or {"action": "status"}, session_id=session)))


def comment(request="test"):
    return {"action": "comment_create", "issue_number": 7,
            "request_id": request, "body": "Bound operation result"}


def test_actual_directory_loader_two_sessions_share_one_app(app_host):
    host = app_host
    assert host.calls == host.key_calls == []  # bind has no credential/network effect
    entry = load(host)
    assert host.calls == host.key_calls == []  # discovery also has no such effect
    assert entry.schema == TOOL_SCHEMA and entry.is_async
    for session in ("one", "two"):
        result = invoke(host, entry, comment(), session)
        assert result["state"] == "CREATED"
        assert "fixture-token" not in json.dumps(result)
        assert session not in json.dumps(result)
    assert len(host.key_calls) == 1
    assert len([c for c in host.calls if c[1].endswith("/access_tokens")]) == 1
    assert {c["user"]["login"] for c in host.comments} == {ACTOR}
    for session, item in zip(("one", "two"), host.comments):
        assert "operation=operation-" + session in item["body"]
        assert "session-sha256=" + hashlib.sha256(session.encode()).hexdigest()[:16] in item["body"]
    assert host.clients["one"].binding.branch != host.clients["two"].binding.branch


def test_unbound_native_discovery_has_no_tool(native):
    native.manager._load_plugin(native.manifest)
    assert native.manager._plugins["mmx_github"].enabled
    assert native.registry.snapshot_registration("mmx_github", scope=str(native.home)) is None


def test_independent_profile_managers_share_app_not_session_scope(app_host, tmp_path):
    from hermes_cli.plugins import PluginContext, PluginManager
    from hermes_cli.plugins_manifest import parse_manifest_file
    first = app_host
    first_entry = load(first)
    home = tmp_path / "second-profile"
    package = home / "plugins/mmx_github"
    shutil.copytree(first.package, package)
    (home / "config.yaml").write_text("plugins:\n  isolation: in_process\n")
    manager = PluginManager(scope_key=str(home))
    manifest = parse_manifest_file(package / "plugin.yaml", package, "user", "")
    with first.scope(home):
        profile = PluginContext(manifest, manager).profile_name
    second_client = HermesGitHubApp(
        replace(first.clients["two"].binding, profile_id=profile),
        client=first.clients["two"]._client)
    second_binding = HostHermesGitHubBinding(
        profile_id=profile,
        resolve_client=lambda session: second_client if session == "two" else None,
        currentness_guard=lambda: True)
    slot = bind_native_host(manager, binding=second_binding, issuer=first.issuer,
                            app_bot_login=ACTOR, package_path=package)
    second = SimpleNamespace(manager=manager, manifest=manifest, home=home,
                             slot=slot, registry=first.registry, scope=first.scope)
    try:
        second_entry = load(second)
        assert first_entry is not second_entry
        assert invoke(second, second_entry, comment("second"), "one")["state"] == "REFUSED"
        assert first.calls == []
        assert invoke(first, first_entry, comment("first"), "one")["state"] == "CREATED"
        assert invoke(second, second_entry, comment("second"), "two")["state"] == "CREATED"
        manager.unload()
        assert invoke(first, first_entry)["state"] == "AVAILABLE"
        assert {item["user"]["login"] for item in first.comments} == {ACTOR}
        assert len(first.key_calls) == 1
    finally:
        slot.close()
        manager.unload()


def test_native_collision_preserves_existing_tool(app_host):
    from hermes_cli.plugins import PluginContext
    from hermes_cli.plugins_manifest import PluginManifest
    host = app_host
    original = lambda args: "existing tool"
    foreign = PluginContext(PluginManifest(name="foreign", version="1",
                            source="user", path=str(host.home), key="foreign"),
                            host.manager)
    handle = foreign.register_tool(name="mmx_github", toolset="existing",
                                   schema={"name": "mmx_github"}, handler=original)
    entry = host.registry.snapshot_registration("mmx_github", scope=str(host.home))
    host.manager._load_plugin(host.manifest)
    assert not host.manager._plugins["mmx_github"].enabled
    assert str(host.slot.registration_error) == "GITHUB_NATIVE_COLLISION"
    assert host.registry.snapshot_registration("mmx_github", scope=str(host.home)) is entry
    assert entry.handler is original
    assert host.calls == []
    handle.dispose()


@pytest.mark.parametrize("failure", ["wrong_session", "wrong_profile", "expired", "revoked", "wrong_actor", "wrong_issuer"])
def test_invalid_binding_never_reads_key_or_writes(app_host, failure):
    host = app_host
    entry = load(host)
    session = "one"
    if failure == "wrong_session":
        session = "unknown"
    elif failure == "expired":
        host.clock[0] += 121
    elif failure == "revoked":
        host.live["host"] = False
    else:
        change = {"wrong_profile": {"profile_id": "foreign"},
                  "wrong_actor": {"app_bot_login": "another[bot]"},
                  "wrong_issuer": {"token_source": GitHubAppInstallationTokens(
                      app_id=999, installation_id=456, repository=REPO,
                      private_key_source=lambda: b"unused", permissions=AUTHORING_PERMISSIONS)}}[failure]
        host.clients["one"].binding = replace(host.clients["one"].binding, **change)
    assert invoke(host, entry, comment(), session)["state"] == "REFUSED"
    assert host.calls == host.key_calls == []


@pytest.mark.parametrize("field", ["token", "private_key", "repository", "repo", "role", "session_id", "app_id", "installation_id"])
def test_model_cannot_select_identity_or_credentials(app_host, field):
    entry = load(app_host)
    assert field not in entry.schema["parameters"]["properties"]
    assert invoke(app_host, entry, {**comment(), field: "forged"})["state"] == "REFUSED"
    assert app_host.calls == app_host.key_calls == []


def test_missing_sealed_key_is_opaque_and_sends_nothing(app_host):
    entry = load(app_host)
    def missing():
        raise PermissionError("private custodian diagnostic must not escape")
    app_host.issuer._private_key_source = missing
    result = invoke(app_host, entry, comment())
    assert result["state"] == "UNAVAILABLE"
    assert "private custodian" not in json.dumps(result)
    assert app_host.calls == []


def test_wrong_returned_actor_is_unknown_after_one_write(app_host):
    entry = load(app_host)
    app_host.actor[0] = "unexpected[bot]"
    assert invoke(app_host, entry, comment())["state"] == "EFFECT_UNKNOWN"
    assert len(app_host.comments) == 1


def test_source_path_outside_grant_never_issues_token(app_host):
    entry = load(app_host)
    result = invoke(app_host, entry, {"action": "file_commit", "expected_head": BASE,
                                    "path": "config/authority_map.yml", "content": "bad", "message": "bad"})
    assert result["state"] == "REFUSED"
    assert app_host.calls == app_host.key_calls == []


def test_unload_invalidates_original_handler(app_host):
    entry = load(app_host)
    assert app_host.manager.unload("mmx_github")
    assert app_host.registry.snapshot_registration("mmx_github", scope=str(app_host.home)) is None
    assert invoke(app_host, entry, comment())["state"] == "REFUSED"
    assert app_host.calls == []


def test_native_unload_rebind_reload_keeps_old_handler_revoked(app_host):
    host = app_host
    old_slot = host.slot
    old_entry = load(host)
    assert host.manager.unload("mmx_github")
    host.slot = bind_native_host(host.manager, binding=host.binding, issuer=host.issuer,
                                app_bot_login=ACTOR, package_path=host.package)
    assert host.slot is not old_slot
    new_entry = load(host)
    old_slot.close()  # late duplicate cleanup cannot tear down the new binding
    assert invoke(host, old_entry, comment())["state"] == "REFUSED"
    assert host.calls == []
    assert invoke(host, new_entry, comment())["state"] == "CREATED"
    host.slot.close()


def test_uncertain_cleanup_retains_binding_without_retry(app_host, monkeypatch):
    host = app_host
    entry = load(host)
    attempts = []
    def fail(registration):
        attempts.append(True)
        raise OSError("fixture disposal uncertainty")
    monkeypatch.setattr(type(host.slot.registration), "dispose", fail)
    host.manager.unload("mmx_github")
    assert host.slot.cleanup_error is not None
    assert attempts == [True]
    host.slot.close()
    assert attempts == [True]
    with pytest.raises(RuntimeError, match="HOST_ALREADY_BOUND"):
        bind_native_host(host.manager, binding=host.binding, issuer=host.issuer,
                         app_bot_login=ACTOR, package_path=host.package)
    assert invoke(host, entry, comment())["state"] == "REFUSED"
    assert host.calls == []


def test_rebind_and_registration_replay_are_refused(app_host):
    host = app_host
    entry = load(host)
    assert bind_native_host(host.manager, binding=host.binding, issuer=host.issuer,
                            app_bot_login=ACTOR, package_path=host.package) is host.slot
    with pytest.raises(RuntimeError, match="HOST_ALREADY_BOUND"):
        bind_native_host(host.manager, binding=replace(host.binding), issuer=host.issuer,
                         app_bot_login=ACTOR, package_path=host.package)
    with host.scope(host.home), pytest.raises(RuntimeError, match="ORIGINAL_REGISTRATION_RETAINED"):
        register_from_host(host.ctx, package_path=host.package)
    assert host.registry.snapshot_registration("mmx_github", scope=str(host.home)) is entry


def test_registration_error_retains_original_context_and_prevents_retry(app_host, monkeypatch):
    import integrations.hermes_github_plugin_host as module
    error = RuntimeError("fixture registration uncertainty")
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(module, "register_native_tool", fail)
    app_host.manager._load_plugin(app_host.manifest)
    assert not app_host.manager._plugins["mmx_github"].enabled
    assert app_host.slot.registration_error is error
    assert app_host.slot.registration_context._manager is app_host.manager
    with app_host.scope(app_host.home), pytest.raises(RuntimeError, match="ORIGINAL_REGISTRATION_RETAINED"):
        register_from_host(app_host.ctx, package_path=app_host.package)
    app_host.slot.close()
    with pytest.raises(RuntimeError, match="HOST_ALREADY_BOUND"):
        bind_native_host(app_host.manager, binding=app_host.binding, issuer=app_host.issuer,
                         app_bot_login=ACTOR, package_path=app_host.package)
    assert app_host.calls == []


@pytest.mark.parametrize("failure", ["profile", "package", "source", "host_isolation"])
def test_native_owner_mismatch_does_not_register(app_host, failure):
    host = app_host
    if failure == "profile":
        host.slot._binding = replace(host.binding, profile_id="foreign")
    elif failure == "package":
        host.manifest.path = str(host.home)
    elif failure == "source":
        host.manifest.source = "bundled"
    else:
        (host.home / "config.yaml").write_text("plugins:\n  isolation: host\n")
    with host.scope(host.home), pytest.raises(RuntimeError):
        register_from_host(host.ctx, package_path=host.package)
    assert not host.slot.registration_attempted
    assert host.registry.snapshot_registration("mmx_github", scope=str(host.home)) is None
    assert host.calls == []
