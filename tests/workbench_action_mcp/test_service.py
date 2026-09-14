from __future__ import annotations

import asyncio
import dataclasses
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

from integrations.workbench_action_mcp.contracts import ActionCaller, ActionTokenCodec
from integrations.workbench_action_mcp.patch_port import create_text_patch_port
from integrations.workbench_action_mcp.service import (
    SERVICE_SCHEMA,
    ServiceState,
    create_runtime,
    is_ready,
    load_service_config,
    parse_service_config,
    reserve_loopback_socket,
)


def _document(tmp_path: Path) -> tuple[dict[str, object], Path, Path]:
    project = tmp_path / "project"
    audit = tmp_path / "audit"
    artifacts = tmp_path / "artifacts"
    project.mkdir(mode=0o700)
    audit.mkdir(mode=0o700)
    artifacts.mkdir(mode=0o700)
    subject = "a" * 64
    client = "b" * 64
    now_ms = int(time.time() * 1000)
    policy = {
        "schema": "mastermind.business_mcp_auth_policy.v1",
        "policy_id": "fixture.workbench.action.service",
        "resource": "https://workbench-action.example/mcp",
        "resource_metadata_url": "https://workbench-action.example/.well-known/oauth-protected-resource/mcp",
        "issuer": "https://identity.workbench-action.example",
        "authorization_servers": ["https://identity.workbench-action.example"],
        "jwks_uri": "https://identity.workbench-action.example/jwks",
        "required_scopes": ["workbench.action"],
        "allowed_subject_digests": [subject],
        "allowed_algorithms": ["RS256"],
        "clock_skew_seconds": 0,
        "max_token_lifetime_seconds": 3600,
        "jwks_cache_ttl_seconds": 60,
        "unknown_kid_refresh_cooldown_seconds": 1,
        "fetch_failure_backoff_seconds": 1,
    }
    policy_file = tmp_path / "policy.json"
    policy_file.write_text(json.dumps(policy))
    os.chmod(policy_file, 0o600)
    action_key_file = tmp_path / "action-key.hex"
    action_key_file.write_text("9" * 64 + "\n")
    os.chmod(action_key_file, 0o600)
    document: dict[str, object] = {
        "schema": SERVICE_SCHEMA,
        "policy_file": str(policy_file),
        "project_root": str(project),
        "audit_directory": str(audit),
        "artifact_directory": str(artifacts),
        "host_id": "c" * 64,
        "action_key_file": str(action_key_file),
        "bind_host": "127.0.0.1",
        "bind_port": 19443,
        "incoming_authority": "127.0.0.1:19443",
        "max_concurrency": 2,
        "io_timeout_seconds": 5.0,
        "close_timeout_seconds": 5.0,
        "action_ttl_ms": 60_000,
        "lease": {
            "expected_subject_digest": subject,
            "expected_client_ref": client,
            "resource": policy["resource"],
            "required_scopes": ["workbench.action"],
            "project_ref": "project:" + "1" * 64,
            "context_ref": "context:" + "2" * 64,
            "responsibility_ref": "responsibility:" + "3" * 64,
            "operation_ref": "operation:" + "4" * 64,
            "owner_ref": "owner:" + "5" * 64,
            "generation": "generation:" + "6" * 64,
            "allowed_paths": ["sample.py"],
            "committed_head": "7" * 40,
            "lease_expires_at_ms": now_ms + 300_000,
        },
    }
    return document, project, audit


def test_closed_service_config_loads_from_secure_file(tmp_path: Path) -> None:
    document, _, _ = _document(tmp_path)
    config_file = tmp_path / "service.json"
    config_file.write_text(json.dumps(document))
    os.chmod(config_file, 0o600)
    loaded = load_service_config(str(config_file))
    assert loaded.schema == SERVICE_SCHEMA
    assert loaded.allowed_hosts == ("127.0.0.1:19443",)
    assert loaded.lease.required_scopes == ("workbench.action",)
    assert loaded.lease.operation_ref.startswith("operation:")
    assert loaded.artifact_directory.endswith("/artifacts")
    assert loaded.host_id == "c" * 64


def test_service_config_rejects_read_scope_and_extra_keys(tmp_path: Path) -> None:
    document, _, _ = _document(tmp_path)
    wrong_scope = json.loads(json.dumps(document))
    wrong_scope["lease"]["required_scopes"] = ["workbench.read"]
    try:
        parse_service_config(wrong_scope)
    except Exception as error:
        assert getattr(error, "code", None) == "SERVICE_CONFIGURATION_REFUSED"
    else:
        raise AssertionError("read scope was accepted")
    extra = dict(document)
    extra["shell"] = "/bin/zsh"
    try:
        parse_service_config(extra)
    except Exception as error:
        assert getattr(error, "code", None) == "SERVICE_CONFIGURATION_REFUSED"
    else:
        raise AssertionError("generic shell selector was accepted")
    invalid_host = dict(document)
    invalid_host["host_id"] = "host-a"
    try:
        parse_service_config(invalid_host)
    except Exception as error:
        assert getattr(error, "code", None) == "SERVICE_CONFIGURATION_REFUSED"
    else:
        raise AssertionError("non-digest host identity was accepted")


def test_runtime_from_service_config_is_ready_only_while_owned(tmp_path: Path) -> None:
    document, _, _ = _document(tmp_path)
    config = parse_service_config(document)

    async def exercise() -> None:
        runtime = await create_runtime(config)
        state = ServiceState(lifespan_started=True, socket_owned=True)
        assert is_ready(runtime, config, state)
        stable = config.lease
        caller = ActionCaller(
            subject_digest=stable.expected_subject_digest,
            client_ref=stable.expected_client_ref,
            resource=stable.resource,
            scopes=stable.required_scopes,
            expires_at=max(1, stable.lease_expires_at_ms // 1000),
        )
        binding = runtime.resolve_binding(caller, stable.project_ref)
        assert binding is not None
        assert binding.scope.operation_ref == stable.operation_ref
        runtime.revoke()
        assert not is_ready(runtime, config, state)
        await runtime.aclose(timeout=5.0)

    asyncio.run(exercise())


def test_loopback_socket_owner_never_binds_non_loopback(tmp_path: Path) -> None:
    document, _, _ = _document(tmp_path)
    config = dataclasses.replace(parse_service_config(document), bind_port=0)
    sock = reserve_loopback_socket(config, _allow_ephemeral_for_test=True)
    try:
        host, port = sock.getsockname()
        assert host == "127.0.0.1"
        assert port > 0
        assert sock.get_inheritable() is False
    finally:
        sock.close()


def test_action_key_is_stable_across_runtime_restart_for_reconciliation(tmp_path: Path) -> None:
    document, _, _ = _document(tmp_path)
    config = parse_service_config(document)
    stable = config.lease
    caller = ActionCaller(
        subject_digest=stable.expected_subject_digest,
        client_ref=stable.expected_client_ref,
        resource=stable.resource,
        scopes=stable.required_scopes,
        expires_at=max(1, stable.lease_expires_at_ms // 1000),
    )

    async def exercise() -> None:
        first = await create_runtime(config)
        prepare, commit, _ = create_text_patch_port(
            resolve_binding=first.resolve_binding,
            clock_ms=lambda: int(time.time() * 1000),
            run_io=first.run_io,
            token_codec=ActionTokenCodec(bytes.fromhex("9" * 64)),
            artifact_store=first.artifact_store,
            host=first.host_binding,
            action_ttl_ms=config.action_ttl_ms,
        )
        prepared = await prepare(
            caller,
            {
                "project_ref": stable.project_ref,
                "relative_path": "sample.py",
                "mode": "CREATE",
                "new_text": "hello\n",
            },
        )
        applied = await commit(caller, prepared["action_ref"])
        assert applied["effect_state"] == "APPLIED"
        first_store_identity = (first.artifact_store.device, first.artifact_store.inode)
        first_boot = first.host_binding.boot_session_id
        await first.aclose(timeout=5.0)

        second = await create_runtime(config)
        _, _, reconcile = create_text_patch_port(
            resolve_binding=second.resolve_binding,
            clock_ms=lambda: int(time.time() * 1000),
            run_io=second.run_io,
            token_codec=ActionTokenCodec(bytes.fromhex("9" * 64)),
            artifact_store=second.artifact_store,
            host=second.host_binding,
            action_ttl_ms=config.action_ttl_ms,
        )
        observed = await reconcile(caller, prepared["action_ref"])
        assert observed["effect_state"] == "APPLIED"
        assert (second.artifact_store.device, second.artifact_store.inode) == first_store_identity
        assert second.host_binding.boot_session_id == first_boot
        await second.aclose(timeout=5.0)

    asyncio.run(exercise())


def test_launcher_describe_is_dependency_free_and_truthful() -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "mastermind_workbench_action_server.py"
    completed = subprocess.run(
        [sys.executable, "-S", str(script), "--describe"],
        cwd="/",
        env={"PATH": os.environ.get("PATH", "")},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=5,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    observed = json.loads(completed.stdout)
    assert observed == {
        "capability": "BUILT_NOT_PROVEN",
        "config_schema": "mastermind.workbench_action_service.v1",
        "installed": False,
        "mode": "configured-loopback-service",
        "scope": "workbench.action",
        "tools": [
            "prepare_text_patch",
            "commit_text_patch",
            "reconcile_text_patch",
        ],
    }


def test_service_config_does_not_accept_ephemeral_port_in_production(tmp_path: Path) -> None:
    document, _, _ = _document(tmp_path)
    document["bind_port"] = 0
    try:
        parse_service_config(document)
    except Exception as error:
        assert getattr(error, "code", None) == "SERVICE_CONFIGURATION_REFUSED"
    else:
        raise AssertionError("ephemeral production port was accepted")
