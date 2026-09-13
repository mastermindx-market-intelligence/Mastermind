from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from integrations.business_mcp_auth.contracts import load_resource_policy
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.workbench_action_mcp.contracts import ActionCaller, ActionTokenCodec
from integrations.workbench_action_mcp.patch_port import create_text_patch_port
from integrations.workbench_action_mcp.runtime import (
    StableWorkbenchActionLease,
    WorkbenchActionRuntime,
)


class _Keys:
    def __init__(self) -> None:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        self.jwk.update(kid="fixture", alg="RS256", use="sig")

    async def key_for(self, kid):
        if kid != "fixture":
            raise ValueError("unknown key")
        return self.jwk


def _policy(subject: str):
    return load_resource_policy(
        {
            "schema": "mastermind.business_mcp_auth_policy.v1",
            "policy_id": "fixture.workbench.action.runtime",
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
    )


def test_runtime_executes_patch_through_shared_bounded_executor(tmp_path: Path) -> None:
    project = tmp_path / "project"
    audit = tmp_path / "audit"
    project.mkdir(mode=0o700)
    audit.mkdir(mode=0o700)
    target = project / "sample.py"
    original = b"value = 1\n"
    target.write_bytes(original)

    now_seconds = 1_800_000_000
    now_ms = now_seconds * 1000
    subject = "a" * 64
    client = "b" * 64
    policy = _policy(subject)
    auth = JwtAuthenticator(policy=policy, jwks_cache=_Keys())
    lease = StableWorkbenchActionLease(
        expected_subject_digest=subject,
        expected_client_ref=client,
        resource=policy.resource,
        required_scopes=("workbench.action",),
        project_ref="project:" + "1" * 64,
        context_ref="context:" + "2" * 64,
        responsibility_ref="responsibility:" + "3" * 64,
        operation_ref="operation:" + "4" * 64,
        owner_ref="owner:" + "5" * 64,
        generation="generation:" + "6" * 64,
        allowed_paths=("sample.py",),
        committed_head="7" * 40,
        lease_expires_at_ms=now_ms + 300_000,
    )
    project_fd = os.open(project, os.O_RDONLY | os.O_DIRECTORY)
    audit_fd = os.open(audit, os.O_RDONLY | os.O_DIRECTORY)
    token_key = b"z" * 32
    runtime = None
    try:
        runtime = WorkbenchActionRuntime.open(
            authenticator=auth,
            policy=policy,
            now=lambda: now_seconds,
            clock_ms=lambda: now_ms,
            project_directory_fd=project_fd,
            audit_directory_fd=audit_fd,
            lease=lease,
            action_token_key=token_key,
            allowed_hosts=("127.0.0.1:9443",),
            max_concurrency=1,
            io_timeout_seconds=5.0,
            action_ttl_ms=60_000,
        )
        caller = ActionCaller(
            subject_digest=subject,
            client_ref=client,
            resource=policy.resource,
            scopes=("workbench.action",),
            expires_at=now_seconds + 600,
        )
        binding = runtime.resolve_binding(caller, lease.project_ref)
        assert binding is not None
        assert binding.scope.root_device == os.fstat(project_fd).st_dev

        prepare, commit, reconcile = create_text_patch_port(
            resolve_binding=runtime.resolve_binding,
            clock_ms=lambda: now_ms,
            run_io=runtime.run_io,
            token_codec=ActionTokenCodec(token_key),
            action_ttl_ms=60_000,
        )

        async def exercise() -> None:
            prepared = await prepare(
                caller,
                {
                    "project_ref": lease.project_ref,
                    "relative_path": "sample.py",
                    "mode": "REPLACE",
                    "expected_sha256": hashlib.sha256(original).hexdigest(),
                    "old_text": "value = 1",
                    "new_text": "value = 2",
                },
            )
            result = await commit(caller, prepared["action_ref"])
            assert result["effect_state"] == "APPLIED"
            observed = await reconcile(caller, prepared["action_ref"])
            assert observed["effect_state"] == "APPLIED"
            await runtime.aclose(timeout=5.0)

        asyncio.run(exercise())
        assert target.read_text() == "value = 2\n"
        assert runtime.resolve_binding(caller, lease.project_ref) is None
    finally:
        if runtime is not None:
            try:
                asyncio.run(runtime.aclose(timeout=1.0))
            except Exception:
                pass
        os.close(project_fd)
        os.close(audit_fd)
