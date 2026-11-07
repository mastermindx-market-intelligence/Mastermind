"""Credential narrowing at the original runtime, action ledger and relay.

These source tests use disposable files and fixture relay responses. The real
pinned Playwright/Fernet composition is qualified separately in ordinary CI.
No private account, installed host, socket, or browser is accessed here.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
from pathlib import Path

import pytest

from integrations.workbench_browser_mcp.credential_use import (
    CREDENTIAL_ACTION_SCHEMA, CREDENTIAL_GRANT_SCHEMA, CREDENTIAL_USE_SCHEMA,
    CREDENTIAL_TOOL, CredentialUseRefused, credential_result,
    credential_selection_digest, parse_credential_grant, validate_credential_result,
)
from integrations.workbench_browser_mcp.browser_port import BrowserPortRefused
from integrations.workbench_browser_mcp.relay import BrowserRelayError, McpStdioSession, McpSessionReceipt
from integrations.workbench_browser_mcp.vault_files import capture_existing_vault
from tests.test_workbench_browser_port import _fixture


def grant(directory: Path, *, expires=7500):
    info = directory.stat()
    return {
        "schema": CREDENTIAL_GRANT_SCHEMA, "grant_ref": "credential:" + "e" * 32,
        "backend": "hermes-fernet-v1", "vault_directory": str(directory),
        "vault_device": info.st_dev, "vault_inode": info.st_ino,
        "item_ref": "vault_0123456789ab", "account_identifier": "fixture@example.test",
        "origin": "https://vault.test", "expires_at_ms": expires,
    }


def private_use(selected, *, resource_id="c" * 32, expires=7000):
    return {"schema": CREDENTIAL_USE_SCHEMA, "grant": selected,
            "resource_id": resource_id, "expires_at_ms": expires,
            "binding_sha256": "a" * 64}


def vault_files(tmp_path):
    root = tmp_path / "vault"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    for name, value in (("vault.key", "A" * 43 + "="), ("vault.json.enc", "fixture-ciphertext")):
        (root / name).write_text(value)
        (root / name).chmod(0o600)
    return root


@pytest.mark.parametrize("state,code", [
    ("APPLIED", "FILLED"), ("NOT_APPLIED", "TARGET_REFUSED"),
    ("EFFECT_UNKNOWN", "FILL_UNCERTAIN"),
])
def test_credential_action_uses_original_ledger_and_never_replays(tmp_path, state, code):
    calls = []
    def relay(_path, request, *, timeout):
        calls.append(request)
        return {"schema": "mastermind.workbench_browser_relay_response.v1",
                "request_id": request["request_id"], "resource_id": "c" * 32,
                "ok": True, "result": credential_result(state, code)}
    fd, caller, port, browser_ref = _fixture(tmp_path, relay)
    selected = private_use(grant(vault_files(tmp_path)))
    port._resolve_credential_use = lambda *_: selected
    try:
        action = port.prepare_credential_fill(caller, browser_ref, selected["grant"]["grant_ref"])
        decoded = port._codec.decode_action(action, now_ms=2000)
        assert decoded.schema == CREDENTIAL_ACTION_SCHEMA
        assert json.loads(decoded.arguments_json) == {
            "grant_ref": selected["grant"]["grant_ref"],
            "selection_sha256": credential_selection_digest(selected),
        }
        assert decoded.expires_at_ms <= selected["expires_at_ms"]
        assert port.run_action(caller, browser_ref, action)["effect_state"] == state
        repeat = port.run_action(caller, browser_ref, action)
        assert repeat["effect_state"] == state and repeat["reconciled"]
        assert len(calls) == 1 and calls[0]["kind"] == "credential_fill"
        assert "tool" not in calls[0] and "arguments" not in calls[0]
        for path in (tmp_path / "artifacts").iterdir():
            if path.is_file():
                raw = path.read_bytes()
                assert selected["grant"]["account_identifier"].encode() not in raw
                assert b"fixture-ciphertext" not in raw
    finally:
        os.close(fd)


@pytest.mark.parametrize("mutation", [
    {"item_ref": "vault_abcdef012345"}, {"account_identifier": "other@example.test"},
    {"origin": "https://other.test"}, {"vault_inode": 123456789},
])
def test_prepared_action_freezes_full_selection_not_reusable_grant_label(tmp_path, mutation):
    fd, caller, port, browser_ref = _fixture(tmp_path, lambda *_a, **_k: pytest.fail("dispatch"))
    selected = private_use(grant(vault_files(tmp_path)))
    port._resolve_credential_use = lambda *_: selected
    try:
        action = port.prepare_credential_fill(caller, browser_ref, selected["grant"]["grant_ref"])
        selected["grant"] = {**selected["grant"], **mutation}
        refused = port.run_action(caller, browser_ref, action)
        assert refused["effect_state"] == "NOT_APPLIED"
        assert port.run_action(caller, browser_ref, action)["reconciled"]
    finally:
        os.close(fd)


def test_lost_credential_reply_retains_original_claim_unknown(tmp_path):
    calls = []
    def lost(_path, request, *, timeout):
        calls.append(request)
        raise BrowserRelayError("fixture response loss")
    fd, caller, port, browser_ref = _fixture(tmp_path, lost)
    selected = private_use(grant(vault_files(tmp_path)))
    port._resolve_credential_use = lambda *_: selected
    try:
        action = port.prepare_credential_fill(caller, browser_ref, selected["grant"]["grant_ref"])
        for _ in range(2):
            assert port.run_action(caller, browser_ref, action)["effect_state"] == "EFFECT_UNKNOWN"
        assert len(calls) == 1
        with pytest.raises(BrowserPortRefused):
            port.prepare_action(caller, browser_ref, CREDENTIAL_TOOL, {})
    finally:
        os.close(fd)


@pytest.mark.parametrize("change", [
    {"effect_state": "APPLIED", "code": "ITEM_REFUSED"},
    {"effect_state": "NOT_APPLIED", "code": "FILLED"},
    {"effect_state": "NOT_APPLIED", "code": "FILL_UNCERTAIN"},
    {"effect_state": "EFFECT_UNKNOWN", "code": "TARGET_REFUSED"},
    {"code": []}, {"password": "unexpected-field"},
])
def test_credential_result_is_closed_and_cannot_launder_effect_truth(change):
    with pytest.raises(CredentialUseRefused):
        validate_credential_result({**credential_result("APPLIED", "FILLED"), **change})


@pytest.mark.parametrize("mutation", [
    {"origin": "http://vault.test"}, {"origin": "https://vault.test:443"},
    {"origin": "https://vault.test/"}, {"origin": "https://user@vault.test"},
    {"origin": "https://vault.test."}, {"origin": "https://*.test"},
    {"vault_directory": "/tmp/../vault"}, {"backend": "discover"},
    {"vault_inode": True}, {"account_identifier": " trailing "},
    {"password": "unaccepted"},
])
def test_host_selection_contract_refuses_ambiguity(tmp_path, mutation):
    with pytest.raises(CredentialUseRefused):
        parse_credential_grant({**grant(tmp_path), **mutation})


def test_capture_is_read_only_and_exactly_selected(tmp_path):
    root = vault_files(tmp_path)
    before = {p.name: (p.stat(), p.read_bytes()) for p in root.iterdir()}
    assert capture_existing_vault(grant(root)) == {"key": "A" * 43 + "=", "ciphertext": "fixture-ciphertext"}
    assert set(before) == {p.name for p in root.iterdir()}
    for path in root.iterdir():
        info, raw = before[path.name]
        assert path.read_bytes() == raw
        assert path.stat().st_ino == info.st_ino
        assert path.stat().st_mtime_ns == info.st_mtime_ns


@pytest.mark.parametrize("fault", ["directory-mode", "key-mode", "key-link", "cipher-symlink", "directory-swap", "oversize"])
def test_capture_refuses_unsafe_or_replaced_files(tmp_path, fault):
    root = vault_files(tmp_path)
    selected = grant(root)
    if fault == "directory-mode": root.chmod(0o755)
    elif fault == "key-mode": (root / "vault.key").chmod(0o644)
    elif fault == "key-link": os.link(root / "vault.key", tmp_path / "extra-key")
    elif fault == "cipher-symlink":
        (root / "vault.json.enc").rename(tmp_path / "cipher")
        (root / "vault.json.enc").symlink_to(tmp_path / "cipher")
    elif fault == "directory-swap":
        root.rename(tmp_path / "old-vault")
        root.mkdir(mode=0o700)
    elif fault == "oversize": (root / "vault.json.enc").write_bytes(b"A" * (1024 * 1024 + 1))
    with pytest.raises(CredentialUseRefused, match="^CREDENTIAL_USE_REFUSED$"):
        capture_existing_vault(selected)


def test_capture_refuses_atomic_key_replacement_during_read(tmp_path, monkeypatch):
    root = vault_files(tmp_path)
    selected = grant(root)
    original = os.read
    swapped = False
    def read(fd, count):
        nonlocal swapped
        data = original(fd, count)
        if not swapped:
            replacement = root / "replacement"
            replacement.write_text("B" * 43 + "=")
            replacement.chmod(0o600)
            replacement.replace(root / "vault.key")
            swapped = True
        return data
    monkeypatch.setattr(os, "read", read)
    with pytest.raises(CredentialUseRefused): capture_existing_vault(selected)


def test_actual_donor_writer_keeps_crypto_dependency_identity_across_vaults(tmp_path):
    from tests.fixtures.hermes_vault.fixture_writer import write_login
    from cryptography.fernet import Fernet
    import sys
    aliases = {name: sys.modules.get(name) for name in ("utils", "hermes_dir_acl", "hermes_constants")}
    for index in range(3):
        root = tmp_path / str(index)
        item = write_login(root, password="synthetic-interop-only")
        document = json.loads(Fernet((root / "vault.key").read_bytes()).decrypt((root / "vault.json.enc").read_bytes()))
        assert document["items"][0]["id"] == item.id
        assert document["items"][0]["secret"]["password"] == "synthetic-interop-only"
    assert all(sys.modules.get(name) is value for name, value in aliases.items())


def test_relay_does_not_read_vault_before_target_ready_and_aborts_same_target(tmp_path, monkeypatch):
    from integrations.workbench_browser_mcp import vault_files as files
    selected = private_use(grant(vault_files(tmp_path)))
    session = McpStdioSession(argv=("/usr/bin/true",), env={}, allowed_tools=frozenset({"browser_snapshot"}),
        expected_tool_schema_digest="d" * 64, credential_enabled=True, credential_launch_guard=lambda: None)
    session._receipt = McpSessionReceipt(1, "d" * 64, ("browser_snapshot",))
    calls = []
    def rpc(method, params):
        calls.append((method, params))
        if method.endswith("prepare"): return credential_result("NOT_APPLIED", "TARGET_REFUSED")
        pytest.fail("not allowed after refusal")
    monkeypatch.setattr(session, "_rpc", rpc)
    monkeypatch.setattr(files, "capture_existing_vault", lambda *_: pytest.fail("premature secret read"))
    assert session.credential_fill(selected, action_id="a" * 32, clock_ms=lambda: 2000)["code"] == "TARGET_REFUSED"
    assert len(calls) == 1
    calls.clear()
    target = "1" * 32
    def ready(method, params):
        calls.append((method, params))
        if method.endswith("prepare"):
            return {"schema": "mastermind.workbench_browser_credential_target.v1", "status": "READY", "target_ref": target}
        assert method.endswith("abort") and params == {"target_ref": target}
        return credential_result("NOT_APPLIED", "VAULT_UNAVAILABLE")
    monkeypatch.setattr(session, "_rpc", ready)
    def unavailable(_): raise CredentialUseRefused()
    monkeypatch.setattr(files, "capture_existing_vault", unavailable)
    assert session.credential_fill(selected, action_id="a" * 32, clock_ms=lambda: 2000)["effect_state"] == "NOT_APPLIED"
    assert [m for m, _ in calls] == ["mastermind/credential_prepare", "mastermind/credential_abort"]


def test_existing_runtime_alone_projects_live_credential_authority(tmp_path):
    from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
    from integrations.workbench_action_mcp.runtime import WorkbenchActionRuntime
    from integrations.workbench_action_mcp.contracts import ActionCaller
    from integrations.workbench_browser_mcp.contracts import BrowserResourceRef
    from tests.workbench_action_mcp.test_runtime import _policy, _lease, _Keys, _open_directories
    _project, _audit, _artifacts, *fds = _open_directories(tmp_path)
    now = 1_800_000_000
    policy = _policy("a" * 64)
    lease = _lease("a" * 64, "b" * 64, policy.resource, now * 1000)
    runtime = None
    try:
        runtime = WorkbenchActionRuntime.open(authenticator=JwtAuthenticator(policy=policy, jwks_cache=_Keys()),
            policy=policy, now=lambda: now, clock_ms=lambda: now * 1000,
            project_directory_fd=fds[0], audit_directory_fd=fds[1], host_artifact_fd=fds[2],
            host_id="c" * 64, lease=lease, action_token_key=b"z" * 32,
            allowed_hosts=("127.0.0.1:9443",), max_concurrency=1, io_timeout_seconds=5,
            action_ttl_ms=60000)
        caller = ActionCaller("a" * 64, "b" * 64, policy.resource, ("workbench.action",), now + 600)
        browser = BrowserResourceRef(schema="mastermind.workbench_browser_ref.v1", start_action_id="c" * 32,
            subject_digest=caller.subject_digest, client_ref=caller.client_ref, resource=caller.resource,
            project_ref=lease.project_ref, context_ref=lease.context_ref, responsibility_ref=lease.responsibility_ref,
            operation_ref=lease.operation_ref, owner_ref=lease.owner_ref, generation=lease.generation,
            host_id=runtime.host_binding.host_id, boot_session_id=runtime.host_binding.boot_session_id,
            relay_pid=4321, relay_start_identity="1700000000.000001", relay_pgid=4321, relay_session_id=4321,
            mode="isolated", profile_ref=None, tool_schema_digest="d" * 64,
            issued_at_ms=now * 1000, expires_at_ms=now * 1000 + 120000)
        selected = parse_credential_grant(grant(vault_files(tmp_path), expires=now * 1000 + 90000))
        assert runtime.resolve_browser_credential_use(caller, browser, selected.grant_ref) is None
        runtime._adopt_browser_credential_grant(selected)
        use = runtime.resolve_browser_credential_use(caller, browser, selected.grant_ref)
        assert use["expires_at_ms"] == selected.expires_at_ms
        assert runtime.services.resolve_browser_credential_use == runtime.resolve_browser_credential_use
        for field, value in (("generation", "generation:" + "f" * 64), ("boot_session_id", "other"),
                             ("host_id", "f" * 64), ("mode", "profile")):
            assert runtime.resolve_browser_credential_use(caller, dataclasses.replace(browser, **{field: value}), selected.grant_ref) is None
        with pytest.raises(CredentialUseRefused): runtime._adopt_browser_credential_grant(selected)
        runtime.revoke()
        assert runtime.resolve_browser_credential_use(caller, browser, selected.grant_ref) is None
    finally:
        if runtime is not None:
            runtime.revoke()
            asyncio.run(runtime.aclose(timeout=5.0))
        for fd in fds: os.close(fd)


def test_v3_service_composes_same_runtime_and_rejects_mixed_source(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    from integrations.workbench_action_mcp import service
    from integrations.workbench_browser_mcp import deployment
    from tests.workbench_action_mcp.test_service import _document
    from tests.workbench_action_mcp.test_browser_service_composition import _browser_block
    document, _, _ = _document(tmp_path)
    document["schema"] = service.SERVICE_SCHEMA_V3
    document["browser"] = _browser_block(tmp_path)
    document["browser"].update(source_root=str(Path(__file__).resolve().parents[1]), python_executable=sys.executable)
    document["credential_grant"] = grant(vault_files(tmp_path), expires=document["lease"]["lease_expires_at_ms"])
    document["credential_runtime"] = {"runtime_root": str(tmp_path / "runtime"), "manifest_sha256": "a" * 64}
    selected = service.parse_service_config(document)
    captured = {}
    def compose(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(server=object())
    monkeypatch.setattr(deployment, "create_browser_deployment", compose)
    async def exercise():
        runtime = await service.create_runtime(selected)
        try:
            assert runtime._browser_credential_grant == selected.credential_grant
            service.create_browser_sibling(runtime, selected)
            assert captured["services"] is runtime.services
            assert captured["host_config"].credential_runtime == selected.browser.credential_runtime
            assert captured["profile_resolver"]("unselected") is None
            mixed = dataclasses.replace(selected, browser=dataclasses.replace(selected.browser, source_root=str(tmp_path / "source")))
            with pytest.raises(service.ServiceConfigurationError): service.create_browser_sibling(runtime, mixed)
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5)
    asyncio.run(exercise())
    for schema in (service.SERVICE_SCHEMA, service.SERVICE_SCHEMA_V2):
        with pytest.raises(service.ServiceConfigurationError):
            service.parse_service_config({**document, "schema": schema})


def test_credential_preparation_uses_actual_existing_jwt_mcp_boundary(monkeypatch):
    from tests import test_workbench_browser_app as fixture
    from integrations.workbench_browser_mcp.credential_use import PREPARE_CREDENTIAL_TOOL
    original = fixture.create_authenticated_browser_server
    calls = []
    async def prepare(caller, browser_ref, grant_ref):
        calls.append((caller, browser_ref, grant_ref))
        return "a" * 32
    def compose(**kwargs):
        return original(**kwargs, prepare_credential_fill=prepare)
    monkeypatch.setattr(fixture, "create_authenticated_browser_server", compose)
    async def exercise():
        instance = fixture.WorkbenchBrowserAppTests()
        await instance.asyncSetUp()
        try:
            args = {"browser_ref": instance.browser_ref, "grant_ref": "credential:" + "e" * 32}
            denied = await instance.rpc("tools/call", {"name": PREPARE_CREDENTIAL_TOOL, "arguments": args})
            assert denied.status_code in (401, 403) and not calls
            offered = instance.result(await instance.rpc("tools/list", token=instance.token()))
            schema = next(row["inputSchema"] for row in offered["tools"] if row["name"] == PREPARE_CREDENTIAL_TOOL)
            assert set(schema["properties"]) == {"browser_ref", "grant_ref"}
            result = await instance.tool_call(PREPARE_CREDENTIAL_TOOL, args)
            assert not result.get("isError", False)
            assert result["structuredContent"]["action_ref"] == "a" * 32
            assert len(calls) == 1 and calls[0][0].subject_digest == instance.subject
            rejected = await instance.tool_call(PREPARE_CREDENTIAL_TOOL, {**args, "password": "unaccepted-fixture"})
            assert rejected["isError"] and len(calls) == 1
            assert "unaccepted-fixture" not in json.dumps(instance.receipts)
        finally:
            await instance.asyncTearDown()
    asyncio.run(exercise())
