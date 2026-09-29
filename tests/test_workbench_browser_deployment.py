from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path

from integrations.business_mcp_auth.contracts import load_resource_policy, subject_digest
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.workbench_action_mcp.action_artifacts import (
    ActionHostBinding,
    adopt_artifact_store,
)
from integrations.workbench_action_mcp.contracts import (
    ActionCaller,
    ActionScope,
    ProjectActionBinding,
)
from integrations.workbench_action_mcp.deployment import RuntimeServices
from integrations.workbench_browser_mcp.deployment import (
    BrowserDeployment,
    BrowserPorts,
    create_browser_deployment,
    create_browser_ports,
)
from integrations.workbench_browser_mcp.resource_port import BrowserHostConfig


class Keys:
    async def key_for(self, _kid):
        raise ValueError("not used in composition test")


class Audit:
    def emit(self, _event):
        return None


def _private(path: Path) -> Path:
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def _fixture(tmp_path: Path):
    artifact = _private(tmp_path / "artifacts")
    fd = os.open(artifact, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    os.set_inheritable(fd, False)
    store = adopt_artifact_store(fd)

    issuer = "https://identity.workbench-browser.example"
    resource = "https://workbench-browser.example/mcp"
    subject = subject_digest(issuer=issuer, subject="operator-a")
    policy = load_resource_policy(
        {
            "schema": "mastermind.business_mcp_auth_policy.v1",
            "policy_id": "fixture.workbench.browser",
            "resource": resource,
            "resource_metadata_url": resource.replace("/mcp", "/.well-known/oauth-protected-resource/mcp"),
            "issuer": issuer,
            "authorization_servers": [issuer],
            "jwks_uri": issuer + "/jwks",
            "required_scopes": ["workbench.action"],
            "allowed_subject_digests": [subject],
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 0,
            "max_token_lifetime_seconds": 3600,
            "jwks_cache_ttl_seconds": 60,
            "unknown_kid_refresh_cooldown_seconds": 1,
            "fetch_failure_backoff_seconds": 1,
        }
    )
    auth = JwtAuthenticator(policy=policy, jwks_cache=Keys())
    caller = ActionCaller(
        subject_digest=subject,
        client_ref="fixture-client",
        resource=resource,
        scopes=("workbench.action",),
        expires_at=1000,
    )
    scope = ActionScope(
        root_fd=99,
        root_device=1,
        root_inode=2,
        context_ref="context:browser",
        responsibility_ref="responsibility:browser",
        operation_ref="operation:browser",
        owner_ref="owner:browser",
        generation="generation:browser",
        allowed_paths=(),
        expires_at_ms=60_000,
    )
    binding = ProjectActionBinding(caller=caller, project_ref="project:browser", scope=scope)
    run_calls = []

    async def run_io(operation):
        run_calls.append(operation)
        return operation()

    services = RuntimeServices(
        authenticator=auth,
        policy=policy,
        now=lambda: 2,
        clock_ms=lambda: 2000,
        audit_sink=Audit(),
        artifact_store=store,
        host_binding=ActionHostBinding(host_id="b" * 64, boot_session_id="boot:browser"),
        resolve_binding=lambda actual, project: binding
        if actual == caller and project == binding.project_ref
        else None,
        run_io=run_io,
        action_token_key=b"k" * 32,
        allowed_hosts=("127.0.0.1",),
        allowed_origins=(),
        action_ttl_ms=30_000,
    )
    source = _private(tmp_path / "source")
    relay = _private(tmp_path / "relay")
    output = _private(tmp_path / "output")
    home = _private(tmp_path / "home")
    temp = _private(tmp_path / "tmp")
    host_config = BrowserHostConfig(
        source_root=source,
        python_executable="/usr/bin/python3",
        node_executable="/usr/bin/node",
        mcp_cli_path="/private/browser/node_modules/@playwright/mcp/cli.js",
        chrome_executable="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        relay_root=relay,
        output_root=output,
        home_dir=str(home),
        tmp_dir=str(temp),
    )
    catalog = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "research"
            / "evidence"
            / "claude_browser_mcp_tools_0_0_79.json"
        ).read_text(encoding="utf-8")
    )
    return fd, services, host_config, catalog, caller, run_calls


def test_deployment_borrows_exact_existing_workbench_owners(tmp_path: Path):
    fd, services, host_config, catalog, caller, run_calls = _fixture(tmp_path)
    try:
        deployment = create_browser_deployment(
            services=services,
            host_config=host_config,
            tool_catalog=catalog,
            profile_resolver=lambda _ref: None,
        )
        assert isinstance(deployment, BrowserDeployment)
        assert deployment.services is services
        assert deployment.resource_port._store is services.artifact_store
        assert deployment.action_port._store is services.artifact_store
        assert deployment.resource_port._host is services.host_binding
        assert deployment.action_port._host_binding is services.host_binding
        assert deployment.resource_port.codec is deployment.action_port.codec
        assert deployment.server is not None

        start_ref = deployment.resource_port.prepare_resource(
            caller,
            project_ref="project:browser",
            mode="isolated",
        )
        assert isinstance(start_ref, str)
        assert run_calls == []
    finally:
        os.close(fd)


def test_async_facade_uses_existing_bounded_run_io(tmp_path: Path):
    fd, services, host_config, catalog, caller, run_calls = _fixture(tmp_path)
    try:
        deployment = create_browser_deployment(
            services=services,
            host_config=host_config,
            tool_catalog=catalog,
            profile_resolver=lambda _ref: None,
        )

        import asyncio

        start_ref = asyncio.run(
            deployment.prepare_resource(
                caller, "project:browser", "isolated", None
            )
        )
        assert isinstance(start_ref, str)
        assert len(run_calls) == 1

        reconciled = asyncio.run(
            deployment.reconcile_resource(caller, start_ref)
        )
        assert reconciled["effect_state"] == "NOT_APPLIED"
        assert len(run_calls) == 2
    finally:
        os.close(fd)


def test_deployment_refuses_a_new_browser_permission_plane(tmp_path: Path):
    fd, services, host_config, catalog, _caller, _run_calls = _fixture(tmp_path)
    try:
        browser_policy = dataclasses.replace(
            services.policy,
            required_scopes=("workbench.browser",),
        )
        altered = dataclasses.replace(services, policy=browser_policy)
        try:
            create_browser_deployment(
                services=altered,
                host_config=host_config,
                tool_catalog=catalog,
                profile_resolver=lambda _ref: None,
            )
        except ValueError as error:
            assert "ACTION_SCOPE_REQUIRED" in str(error) or "AUTH_POLICY_BINDING_MISMATCH" in str(error)
        else:
            raise AssertionError("browser-specific permission plane was accepted")
    finally:
        os.close(fd)

def test_ports_can_be_borrowed_without_constructing_web_auth_server(tmp_path: Path):
    fd, services, host_config, catalog, _caller, _run_calls = _fixture(tmp_path)
    try:
        ports = create_browser_ports(
            resolve_binding=services.resolve_binding,
            clock_ms=services.clock_ms,
            action_token_key=services.action_token_key,
            artifact_store=services.artifact_store,
            host_binding=services.host_binding,
            action_ttl_ms=services.action_ttl_ms,
            host_config=host_config,
            profile_resolver=lambda _ref: None,
        )
        assert isinstance(ports, BrowserPorts)
        assert ports.resource_port._store is services.artifact_store
        assert ports.action_port._store is services.artifact_store
        assert ports.resource_port._host is services.host_binding
        assert ports.action_port._host_binding is services.host_binding
        assert ports.resource_port.codec is ports.action_port.codec
        # Tool catalogs belong to the surface adapter, not the resource/effect ports.
        assert catalog["tools"]
    finally:
        os.close(fd)
