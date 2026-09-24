from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
import stat
import threading
import time
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    load_resource_policy,
    subject_digest,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.workbench_read_mcp import observer as observer_module
from integrations.workbench_read_mcp import read_port as read_port_module
from integrations.workbench_read_mcp import runtime as runtime_module
from integrations.workbench_read_mcp.app import ProjectReadRefused, ReadCaller
from integrations.workbench_read_mcp.read_port import create_descriptor_read_port
from integrations.workbench_read_mcp.runtime import (
    RuntimeCloseIncomplete,
    RuntimeCloseUncertain,
    RuntimeClosed,
    RuntimeConfigurationError,
    StableWorkbenchLease,
    WorkbenchReadRuntime,
)

ISSUER = "https://identity.workbench.example"
RESOURCE = "https://workbench.example/mcp"
SUBJECT_RAW = "chairman-workbench"
CLIENT_RAW = "chatgpt-workbench-client"
SUBJECT = subject_digest(issuer=ISSUER, subject=SUBJECT_RAW)
CLIENT = hashlib.sha256(f"{ISSUER}\nclient\n{CLIENT_RAW}".encode()).hexdigest()
PROJECT = "project:" + "3" * 64
CONTEXT = "context:" + "4" * 64
OWNER = "owner:" + "5" * 64
GENERATION = "generation:" + "6" * 64
NOW = int(time.time())


def policy(*, metadata: str | None = None, subjects: tuple[str, ...] = (SUBJECT,)):
    return load_resource_policy(
        {
            "schema": AUTH_POLICY_SCHEMA,
            "policy_id": "workbench.read.runtime",
            "resource": RESOURCE,
            "resource_metadata_url": metadata
            or ("https://workbench.example/.well-known/oauth-protected-resource/mcp"),
            "issuer": ISSUER,
            "authorization_servers": [ISSUER],
            "jwks_uri": ISSUER + "/jwks",
            "required_scopes": ["workbench.read"],
            "allowed_subject_digests": sorted(subjects),
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 0,
            "max_token_lifetime_seconds": 3600,
            "jwks_cache_ttl_seconds": 60,
            "unknown_kid_refresh_cooldown_seconds": 1,
            "fetch_failure_backoff_seconds": 1,
        }
    )


class Keys:
    def __init__(self, value: object) -> None:
        self.value = value

    async def key_for(self, kid: str):
        if kid != "runtime-key":
            raise ValueError("unknown key")
        return self.value


def lease(**changes: object) -> StableWorkbenchLease:
    value = StableWorkbenchLease(
        expected_subject_digest=SUBJECT,
        expected_client_ref=CLIENT,
        resource=RESOURCE,
        required_scopes=("workbench.read",),
        project_ref=PROJECT,
        context_ref=CONTEXT,
        owner_ref=OWNER,
        generation=GENERATION,
        allowed_paths=("source.txt",),
        committed_head="7" * 40,
        lease_expires_at_ms=(NOW + 600) * 1000,
    )
    return dataclasses.replace(value, **changes)


def open_dirs(tmp_path: Path) -> tuple[Path, int, int]:
    project = tmp_path / "project"
    project.mkdir(parents=True)
    (project / "source.txt").write_text(
        "runtime source\nsecond line\n", encoding="utf-8"
    )
    audit = tmp_path / "audit"
    audit.mkdir(mode=0o700)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    return project, os.open(project, flags), os.open(audit, flags)


def authenticator(selected_policy, public_key: object | None = None):
    key = public_key or {"kty": "RSA", "n": "bad", "e": "AQAB"}
    return JwtAuthenticator(policy=selected_policy, jwks_cache=Keys(key))


def create_runtime(tmp_path: Path, *, selected_policy=None, selected_lease=None):
    project, project_fd, audit_fd = open_dirs(tmp_path)
    selected_policy = selected_policy or policy()
    runtime = WorkbenchReadRuntime.open(
        authenticator=authenticator(selected_policy),
        policy=selected_policy,
        now=lambda: NOW,
        clock_ms=lambda: NOW * 1000,
        project_directory_fd=project_fd,
        audit_directory_fd=audit_fd,
        lease=selected_lease or lease(),
        allowed_hosts=("127.0.0.1",),
        max_concurrency=1,
        io_timeout_seconds=1,
    )
    return project, project_fd, audit_fd, runtime


def test_policy_and_stable_identity_refuse_before_resource_acquisition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project, project_fd, audit_fd = open_dirs(tmp_path)
    bad_policy = policy(metadata="https://workbench.example/wrong")
    opened = 0

    def forbidden_open(*_args, **_kwargs):
        nonlocal opened
        opened += 1
        raise AssertionError("resource acquisition happened before validation")

    from integrations.workbench_read_mcp import runtime as runtime_module

    monkeypatch.setattr(runtime_module.os, "open", forbidden_open)
    with pytest.raises(RuntimeConfigurationError):
        WorkbenchReadRuntime.open(
            authenticator=authenticator(bad_policy),
            policy=bad_policy,
            now=lambda: NOW,
            clock_ms=lambda: NOW * 1000,
            project_directory_fd=project_fd,
            audit_directory_fd=audit_fd,
            lease=lease(),
            allowed_hosts=("127.0.0.1",),
        )
    assert opened == 0
    os.close(project_fd)
    os.close(audit_fd)
    monkeypatch.undo()

    _project, project_fd, audit_fd = open_dirs(tmp_path / "second")
    broader = policy(subjects=(SUBJECT, "f" * 64))
    with pytest.raises(RuntimeConfigurationError):
        WorkbenchReadRuntime.open(
            authenticator=authenticator(broader),
            policy=broader,
            now=lambda: NOW,
            clock_ms=lambda: NOW * 1000,
            project_directory_fd=project_fd,
            audit_directory_fd=audit_fd,
            lease=lease(),
            allowed_hosts=("127.0.0.1",),
        )
    os.close(project_fd)
    os.close(audit_fd)


# RS0_F8_INDEPENDENT_REVIEW_RED_20260909
@pytest.mark.parametrize(
    "field", ["expected_subject_digest", "expected_client_ref"]
)
@pytest.mark.parametrize(
    "bad_value",
    [None, b"bytes", True, 17, ("not", "a", "string")],
    ids=["none", "bytes", "bool", "integer", "tuple"],
)
def test_non_string_lease_identity_is_typed_before_resource_acquisition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    bad_value: object,
) -> None:
    _project, project_fd, audit_fd = open_dirs(tmp_path)
    acquisitions = 0

    from integrations.workbench_read_mcp import runtime as runtime_module

    def forbidden_owned_root(_host_fd: int):
        nonlocal acquisitions
        acquisitions += 1
        raise AssertionError("resource acquisition preceded typed validation")

    monkeypatch.setattr(runtime_module, "_open_owned_root", forbidden_owned_root)
    try:
        with pytest.raises(RuntimeConfigurationError):
            WorkbenchReadRuntime.open(
                authenticator=authenticator(policy()),
                policy=policy(),
                now=lambda: NOW,
                clock_ms=lambda: NOW * 1000,
                project_directory_fd=project_fd,
                audit_directory_fd=audit_fd,
                lease=lease(**{field: bad_value}),
                allowed_hosts=("127.0.0.1",),
            )
    finally:
        os.close(project_fd)
        os.close(audit_fd)
    assert acquisitions == 0


# RS0_F3_EXACT_SCOPE_CONTAINER_REVIEW_20260909
class MutableEqualScopeTuple(tuple):
    def __new__(cls):
        instance = super().__new__(cls, ("workbench.read",))
        instance.accepts = True
        return instance

    def __eq__(self, other: object) -> bool:
        return self.accepts and tuple(self) == other


def test_required_scopes_are_exact_types_before_owned_acquisition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from integrations.workbench_read_mcp import runtime as runtime_module

    project, project_fd, audit_fd = open_dirs(tmp_path)
    attempted: list[int] = []

    def forbidden_owned_root(descriptor: int):
        attempted.append(descriptor)
        raise AssertionError("owned resource acquisition must not begin")

    monkeypatch.setattr(runtime_module, "_open_owned_root", forbidden_owned_root)
    candidates = (
        MutableEqualScopeTuple(),
        (type("ScopeString", (str,), {})("workbench.read"),),
    )
    try:
        for required_scopes in candidates:
            with pytest.raises(
                RuntimeConfigurationError, match="require exactly workbench.read"
            ):
                WorkbenchReadRuntime.open(
                    authenticator=authenticator(policy()),
                    policy=policy(),
                    now=lambda: NOW,
                    clock_ms=lambda: NOW * 1000,
                    project_directory_fd=project_fd,
                    audit_directory_fd=audit_fd,
                    lease=lease(required_scopes=required_scopes),
                    allowed_hosts=("127.0.0.1",),
                )
        assert attempted == []
        os.fstat(project_fd)
        os.fstat(audit_fd)
    finally:
        os.close(project_fd)
        os.close(audit_fd)


# RS0_F3_INDEPENDENT_REVIEW_RED_20260909
def test_runtime_owns_stable_lease_snapshot_against_caller_mutation(
    tmp_path: Path,
) -> None:
    supplied_lease = lease()
    _project, project_fd, audit_fd, runtime = create_runtime(
        tmp_path, selected_lease=supplied_lease
    )
    caller = ReadCaller(
        SUBJECT, CLIENT, RESOURCE, ("workbench.read",), NOW + 10
    )
    try:
        object.__setattr__(supplied_lease, "expected_subject_digest", "f" * 64)
        object.__setattr__(
            supplied_lease, "project_ref", "project:" + "9" * 64
        )
        object.__setattr__(supplied_lease, "allowed_paths", ("not-admitted.txt",))

        binding = runtime.resolve_binding(caller, PROJECT)
        assert binding is not None
        assert binding.project_ref == PROJECT
        assert binding.scope.allowed_paths == ("source.txt",)
        assert (
            runtime.resolve_binding(
                dataclasses.replace(caller, subject_digest="f" * 64), PROJECT
            )
            is None
        )
    finally:
        asyncio.run(runtime.aclose(timeout=1))
        os.close(project_fd)
        os.close(audit_fd)


# RS0_F7_TYPED_MAPPING_DISCRIMINATOR_20260909
def test_outer_runtime_maps_audit_acquisition_cleanup_uncertainty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from integrations.business_mcp_auth.audit import (
        AuditAcquisitionUncertain,
        AuditSinkPoisoned,
    )

    _project, project_fd, audit_fd = open_dirs(tmp_path)
    primary = AuditSinkPoisoned("synthetic audit acquisition refusal")
    cleanup = OSError("synthetic audit descriptor cleanup failure")

    def refuse_audit_open(_cls, *_args, **_kwargs):
        raise AuditAcquisitionUncertain(
            "synthetic audit acquisition cleanup uncertainty",
            primary_error=primary,
            cleanup_errors=(cleanup,),
        )

    monkeypatch.setattr(
        runtime_module.DurableAuthAuditSink,
        "open",
        classmethod(refuse_audit_open),
    )
    try:
        with pytest.raises(RuntimeCloseUncertain) as caught:
            WorkbenchReadRuntime.open(
                authenticator=authenticator(policy()),
                policy=policy(),
                now=lambda: NOW,
                clock_ms=lambda: NOW * 1000,
                project_directory_fd=project_fd,
                audit_directory_fd=audit_fd,
                lease=lease(),
                allowed_hosts=("127.0.0.1",),
            )

        assert caught.value.primary_error is primary
        assert caught.value.cleanup_errors == (cleanup,)
        os.fstat(project_fd)
        os.fstat(audit_fd)
    finally:
        os.close(project_fd)
        os.close(audit_fd)


# RS0_F7_RUNTIME_ACQUISITION_REDS_20260909
def test_owned_root_rollback_close_failure_is_runtime_uncertainty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project, project_fd, audit_fd = open_dirs(tmp_path)
    from integrations.workbench_read_mcp import runtime as runtime_module

    real_validate = runtime_module._validate_directory
    real_close = runtime_module.os.close
    validations = 0
    close_calls: list[int] = []

    def refuse_second_validation(value) -> None:
        nonlocal validations
        validations += 1
        real_validate(value)
        if validations == 2:
            raise RuntimeConfigurationError(
                "synthetic post-root-acquisition refusal"
            )

    def close_then_fail(descriptor: int) -> None:
        close_calls.append(descriptor)
        real_close(descriptor)
        raise OSError("synthetic root rollback close failure")

    monkeypatch.setattr(runtime_module, "_validate_directory", refuse_second_validation)
    monkeypatch.setattr(runtime_module.os, "close", close_then_fail)
    try:
        with pytest.raises(RuntimeCloseUncertain) as caught:
            runtime_module._open_owned_root(project_fd)
    finally:
        monkeypatch.setattr(runtime_module.os, "close", real_close)

    assert isinstance(caught.value.primary_error, RuntimeConfigurationError)
    assert len(caught.value.cleanup_errors) == 1
    assert validations == 2 and len(close_calls) == 1
    os.fstat(project_fd)
    os.fstat(audit_fd)
    real_close(project_fd)
    real_close(audit_fd)


def test_runtime_open_cleanup_uncertainty_outranks_configuration_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project, project_fd, audit_fd = open_dirs(tmp_path)
    from integrations.workbench_read_mcp import runtime as runtime_module

    real_audit_close = runtime_module.DurableAuthAuditSink.close
    close_calls = 0

    def configuration_refusal(_services) -> object:
        raise RuntimeConfigurationError(
            "synthetic post-acquisition configuration refusal"
        )

    def close_then_report_uncertainty(sink) -> None:
        nonlocal close_calls
        close_calls += 1
        real_audit_close(sink)
        raise OSError("synthetic audit rollback close failure")

    monkeypatch.setattr(runtime_module, "create_deployment", configuration_refusal)
    monkeypatch.setattr(
        runtime_module.DurableAuthAuditSink, "close", close_then_report_uncertainty
    )
    with pytest.raises(RuntimeCloseUncertain) as caught:
        WorkbenchReadRuntime.open(
            authenticator=authenticator(policy()),
            policy=policy(),
            now=lambda: NOW,
            clock_ms=lambda: NOW * 1000,
            project_directory_fd=project_fd,
            audit_directory_fd=audit_fd,
            lease=lease(),
            allowed_hosts=("127.0.0.1",),
        )

    assert isinstance(caught.value.primary_error, RuntimeConfigurationError)
    assert len(caught.value.cleanup_errors) == 1
    assert close_calls == 1
    os.fstat(project_fd)
    os.fstat(audit_fd)
    os.close(project_fd)
    os.close(audit_fd)


def test_runtime_owns_independent_root_and_request_local_callers(
    tmp_path: Path,
) -> None:
    _project, project_fd, audit_fd, runtime = create_runtime(tmp_path)
    assert runtime.root_fd != project_fd
    assert (os.fstat(runtime.root_fd).st_dev, os.fstat(runtime.root_fd).st_ino) == (
        os.fstat(project_fd).st_dev,
        os.fstat(project_fd).st_ino,
    )

    caller_a = ReadCaller(SUBJECT, CLIENT, RESOURCE, ("workbench.read",), NOW + 10)
    caller_b = dataclasses.replace(caller_a, expires_at=NOW + 40)
    binding_a = runtime.resolve_binding(caller_a, PROJECT)
    binding_b = runtime.resolve_binding(caller_b, PROJECT)
    assert binding_a is not None and binding_b is not None
    assert binding_a.caller == caller_a and binding_b.caller == caller_b
    assert binding_a.caller is not caller_a and binding_b.caller is not caller_b
    assert binding_a.caller.expires_at != binding_b.caller.expires_at
    assert binding_a.scope.root_fd == runtime.root_fd

    for refused in (
        dataclasses.replace(caller_a, subject_digest="f" * 64),
        dataclasses.replace(caller_a, client_ref="f" * 64),
        dataclasses.replace(caller_a, client_ref="oauth-client-unavailable"),
        dataclasses.replace(caller_a, resource="https://other.example/mcp"),
        dataclasses.replace(caller_a, scopes=("workbench.read", "executive.read")),
    ):
        assert runtime.resolve_binding(refused, PROJECT) is None
    assert runtime.resolve_binding(caller_a, "project:" + "9" * 64) is None
    runtime.revoke()
    assert runtime.resolve_binding(caller_b, PROJECT) is None
    runtime.revoke()
    asyncio.run(runtime.aclose(timeout=1))
    os.fstat(project_fd)
    os.fstat(audit_fd)
    with pytest.raises(OSError):
        os.fstat(runtime.root_fd)
    os.close(project_fd)
    os.close(audit_fd)


def test_incomplete_close_retains_owned_resources_until_physical_drain(
    tmp_path: Path,
) -> None:
    _project, project_fd, audit_fd, runtime = create_runtime(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    def block() -> str:
        entered.set()
        if not release.wait(5):
            raise AssertionError("physical read was not released")
        return "done"

    async def scenario() -> None:
        pending = asyncio.create_task(runtime.run_io(block))
        assert await asyncio.to_thread(entered.wait, 1)
        with pytest.raises(RuntimeCloseIncomplete):
            await runtime.aclose(timeout=0.02)
        os.fstat(runtime.root_fd)
        release.set()
        assert await pending == "done"
        await runtime.aclose(timeout=1)

    asyncio.run(scenario())
    with pytest.raises(OSError):
        os.fstat(runtime.root_fd)
    os.fstat(project_fd)
    os.fstat(audit_fd)
    os.close(project_fd)
    os.close(audit_fd)


def test_lease_identity_formats_are_closed_before_open(tmp_path: Path) -> None:
    _project, project_fd, audit_fd = open_dirs(tmp_path)
    for bad in (
        lease(expected_client_ref="oauth-client-unavailable"),
        lease(project_ref="alpha"),
        lease(context_ref="context:" + "A" * 64),
        lease(committed_head="short"),
        lease(allowed_paths=("../secret",)),
        lease(lease_expires_at_ms=NOW * 1000),
    ):
        with pytest.raises(RuntimeConfigurationError):
            WorkbenchReadRuntime.open(
                authenticator=authenticator(policy()),
                policy=policy(),
                now=lambda: NOW,
                clock_ms=lambda: NOW * 1000,
                project_directory_fd=project_fd,
                audit_directory_fd=audit_fd,
                lease=bad,
                allowed_hosts=("127.0.0.1",),
            )
    os.close(project_fd)
    os.close(audit_fd)


def test_real_signed_mcp_read_renew_revoke_and_audit(tmp_path: Path) -> None:
    signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    public.update(kid="runtime-key", alg="RS256", use="sig")
    selected_policy = policy()
    project, project_fd, audit_fd = open_dirs(tmp_path)
    start = int(time.time())
    clock = [start]
    runtime = WorkbenchReadRuntime.open(
        authenticator=authenticator(selected_policy, public),
        policy=selected_policy,
        now=lambda: clock[0],
        clock_ms=lambda: clock[0] * 1000,
        project_directory_fd=project_fd,
        audit_directory_fd=audit_fd,
        lease=lease(lease_expires_at_ms=(start + 600) * 1000),
        allowed_hosts=("127.0.0.1",),
        max_concurrency=1,
        io_timeout_seconds=1,
    )

    def token(expires_at: int) -> str:
        return jwt.encode(
            {
                "iss": ISSUER,
                "sub": SUBJECT_RAW,
                "aud": RESOURCE,
                "iat": start - 1,
                "exp": expires_at,
                "scope": "workbench.read",
                "client_id": CLIENT_RAW,
            },
            signing_key,
            algorithm="RS256",
            headers={"kid": "runtime-key"},
        )

    async def exercise() -> None:
        app = runtime.server.streamable_http_app()
        ready, stop = asyncio.Event(), asyncio.Event()

        async def lifespan() -> None:
            async with app.router.lifespan_context(app):
                ready.set()
                await stop.wait()

        life = asyncio.create_task(lifespan())
        await asyncio.wait_for(ready.wait(), 5)
        headers = {
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-03-26",
        }
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:

            async def rpc(method: str, params: dict, bearer: str):
                return await client.post(
                    "/mcp",
                    headers={**headers, "Authorization": "Bearer " + bearer},
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": method,
                        "params": params,
                    },
                )

            old = token(start + 20)
            renewed = token(start + 300)
            hello = await rpc(
                "initialize",
                {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "runtime-test", "version": "1"},
                },
                old,
            )
            audit_path = tmp_path / "audit" / "auth-audit.jsonl"
            audit_debug = (
                audit_path.read_text(encoding="utf-8")
                if audit_path.exists()
                else "MISSING"
            )
            assert hello.status_code == 200 and "serverInfo" in hello.text, (
                hello.status_code,
                hello.text,
                dict(hello.headers),
                audit_debug,
            )
            tools = await rpc("tools/list", {}, old)
            assert [item["name"] for item in tools.json()["result"]["tools"]] == [
                "read_project_file"
            ]

            arguments = {
                "project_ref": PROJECT,
                "relative_path": "source.txt",
                "line_count": 1,
                "expected_sha256": hashlib.sha256(
                    (project / "source.txt").read_bytes()
                ).hexdigest(),
            }
            for bearer in (old, renewed):
                response = await rpc(
                    "tools/call",
                    {"name": "read_project_file", "arguments": arguments},
                    bearer,
                )
                body = response.json()["result"]
                assert body["isError"] is False
                structured = body["structuredContent"]
                assert set(structured) == {
                    "atomic_workspace_snapshot",
                    "committed_head",
                    "content",
                    "content_bytes",
                    "context_ref",
                    "file_bytes",
                    "file_identity_digest",
                    "file_sha256",
                    "generation",
                    "index_status",
                    "line_end",
                    "line_start",
                    "next_line",
                    "observation_digest",
                    "observed_at_ms",
                    "owner_ref",
                    "project_ref",
                    "relative_path",
                    "status",
                    "total_lines",
                    "truncated",
                    "view_kind",
                }
                assert structured["content"] == "runtime source\n"
                assert structured["content_bytes"] == len("runtime source\n".encode())
                assert structured["file_bytes"] == len(
                    "runtime source\nsecond line\n".encode()
                )
                assert structured["file_sha256"] == arguments["expected_sha256"]
                assert structured["relative_path"] == "source.txt"
                assert structured["project_ref"] == PROJECT
                assert structured["context_ref"] == CONTEXT
                assert structured["owner_ref"] == OWNER
                assert structured["generation"] == GENERATION
                assert structured["committed_head"] == "7" * 40
                assert structured["line_start"] == 0
                assert structured["line_end"] == 1
                assert structured["next_line"] == 1
                assert structured["total_lines"] == 2
                assert structured["truncated"] is True
                assert structured["status"] == "OK"
                assert structured["view_kind"] == "WORKING_TREE"
                assert structured["index_status"] == "NOT_OBSERVED"
                assert structured["atomic_workspace_snapshot"] is False
                assert structured["observed_at_ms"] == start * 1000
                for digest in (
                    structured["file_identity_digest"],
                    structured["observation_digest"],
                ):
                    assert len(digest) == 64
                    assert set(digest) <= set("0123456789abcdef")

            clock[0] = start + 21
            expired = await rpc(
                "tools/call", {"name": "read_project_file", "arguments": arguments}, old
            )
            assert "runtime source" not in expired.text
            still_valid = await rpc(
                "tools/call",
                {"name": "read_project_file", "arguments": arguments},
                renewed,
            )
            assert still_valid.json()["result"]["isError"] is False
            runtime.revoke()
            revoked = await rpc(
                "tools/call",
                {"name": "read_project_file", "arguments": arguments},
                renewed,
            )
            assert revoked.json()["result"]["isError"] is True
            assert "runtime source" not in revoked.text

        stop.set()
        await asyncio.wait_for(life, 5)
        await runtime.aclose(timeout=1)

    asyncio.run(exercise())
    os.fstat(project_fd)
    os.fstat(audit_fd)
    os.close(project_fd)
    os.close(audit_fd)
    audit_lines = (tmp_path / "audit" / "auth-audit.jsonl").read_text().splitlines()
    assert audit_lines
    decoded = [json.loads(line) for line in audit_lines]
    assert any(
        item
        == {
            "accepted": True,
            "code": "accepted",
            "policy_id": selected_policy.policy_id,
            "schema": "mastermind.business_mcp_auth_audit.v1",
        }
        for item in decoded
    )


def test_revoke_during_real_descriptor_read_withholds_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project, project_fd, audit_fd, runtime = create_runtime(tmp_path)
    caller = ReadCaller(SUBJECT, CLIENT, RESOURCE, ("workbench.read",), NOW + 60)
    read = create_descriptor_read_port(
        resolve_binding=runtime.resolve_binding,
        clock_ms=lambda: NOW * 1000,
        run_io=runtime.run_io,
    )
    entered = threading.Event()
    release = threading.Event()
    original_read = observer_module.os.read
    first_chunk = True

    def gated_read(fd: int, size: int) -> bytes:
        nonlocal first_chunk
        chunk = original_read(fd, size)
        if first_chunk and chunk:
            first_chunk = False
            entered.set()
            if not release.wait(5):
                raise AssertionError("descriptor read gate was not released")
        return chunk

    monkeypatch.setattr(observer_module.os, "read", gated_read)

    async def scenario() -> None:
        pending = asyncio.create_task(
            read(caller, {"project_ref": PROJECT, "relative_path": "source.txt"})
        )
        assert await asyncio.to_thread(entered.wait, 1)
        runtime.revoke()
        release.set()
        with pytest.raises(ProjectReadRefused):
            await pending
        await runtime.aclose(timeout=1)

    asyncio.run(scenario())
    os.close(project_fd)
    os.close(audit_fd)


def test_revoke_after_observation_before_await_release_withholds_content(
    tmp_path: Path,
) -> None:
    _project, project_fd, audit_fd, runtime = create_runtime(tmp_path)
    caller = ReadCaller(SUBJECT, CLIENT, RESOURCE, ("workbench.read",), NOW + 60)
    observed = asyncio.Event()
    release = asyncio.Event()

    async def gated_run_io(operation):
        result = await runtime.run_io(operation)
        observed.set()
        await release.wait()
        return result

    read = create_descriptor_read_port(
        resolve_binding=runtime.resolve_binding,
        clock_ms=lambda: NOW * 1000,
        run_io=gated_run_io,
    )

    async def scenario() -> None:
        pending = asyncio.create_task(
            read(caller, {"project_ref": PROJECT, "relative_path": "source.txt"})
        )
        await asyncio.wait_for(observed.wait(), 1)
        runtime.revoke()
        release.set()
        with pytest.raises(ProjectReadRefused):
            await pending
        await runtime.aclose(timeout=1)

    asyncio.run(scenario())
    os.close(project_fd)
    os.close(audit_fd)


def test_concurrent_close_has_one_descriptor_release_owner(tmp_path: Path) -> None:
    _project, project_fd, audit_fd, runtime = create_runtime(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    def block() -> str:
        entered.set()
        if not release.wait(5):
            raise AssertionError("physical read was not released")
        return "done"

    async def scenario() -> None:
        physical = asyncio.create_task(runtime.run_io(block))
        assert await asyncio.to_thread(entered.wait, 1)
        first = asyncio.create_task(runtime.aclose(timeout=1))
        await asyncio.sleep(0)
        second = asyncio.create_task(runtime.aclose(timeout=1))
        await asyncio.sleep(0.02)
        release.set()
        assert await physical == "done"
        outcomes = await asyncio.gather(first, second, return_exceptions=True)
        assert sum(outcome is None for outcome in outcomes) == 1
        refused = [outcome for outcome in outcomes if outcome is not None]
        assert len(refused) == 1
        assert isinstance(refused[0], RuntimeCloseIncomplete)

    asyncio.run(scenario())
    with pytest.raises(OSError):
        os.fstat(runtime.root_fd)
    os.close(project_fd)
    os.close(audit_fd)


# RS0_F5_RELEASE_SEQUENCE_DISCRIMINATORS_20260909
def test_root_drift_runs_one_attest_audit_root_release_sequence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project, project_fd, audit_host_fd, runtime = create_runtime(tmp_path)
    root_fd = runtime.root_fd
    original_mode = stat.S_IMODE(os.fstat(root_fd).st_mode)
    real_drain = runtime._executor.aclose
    real_attest = runtime._validate_live_root_locked
    real_audit_close = runtime._audit_sink.close
    real_os_close = runtime_module.os.close
    events: list[str] = []

    async def drain_then_drift(*, timeout: float) -> None:
        await real_drain(timeout=timeout)
        os.fchmod(root_fd, original_mode | 0o020)

    def recording_attest() -> None:
        events.append("root_attest")
        real_attest()

    def recording_audit_close() -> None:
        events.append("audit_close")
        real_audit_close()

    def recording_os_close(descriptor: int) -> None:
        if descriptor == root_fd:
            events.append("root_close")
        real_os_close(descriptor)

    monkeypatch.setattr(runtime._executor, "aclose", drain_then_drift)
    monkeypatch.setattr(runtime, "_validate_live_root_locked", recording_attest)
    monkeypatch.setattr(runtime._audit_sink, "close", recording_audit_close)
    monkeypatch.setattr(runtime_module.os, "close", recording_os_close)
    try:
        with pytest.raises(RuntimeCloseUncertain) as first:
            asyncio.run(runtime.aclose(timeout=1))
        assert isinstance(first.value.primary_error, RuntimeClosed)
        assert first.value.cleanup_errors == ()
        assert events == ["root_attest", "audit_close", "root_close"]

        with pytest.raises(RuntimeCloseUncertain) as second:
            asyncio.run(runtime.aclose(timeout=1))
        assert second.value is first.value
        assert events == ["root_attest", "audit_close", "root_close"]
    finally:
        monkeypatch.setattr(runtime_module.os, "close", real_os_close)

    with pytest.raises(OSError):
        os.fstat(root_fd)
    os.fstat(project_fd)
    os.fstat(audit_host_fd)
    os.close(project_fd)
    os.close(audit_host_fd)


def test_combined_root_attestation_and_audit_release_failures_are_retained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project, project_fd, audit_host_fd, runtime = create_runtime(tmp_path)
    root_fd = runtime.root_fd
    original_mode = stat.S_IMODE(os.fstat(root_fd).st_mode)
    real_drain = runtime._executor.aclose
    real_audit_close = runtime._audit_sink.close
    audit_failure = OSError("synthetic audit release uncertainty")
    calls = 0

    async def drain_then_drift(*, timeout: float) -> None:
        await real_drain(timeout=timeout)
        os.fchmod(root_fd, original_mode | 0o020)

    def close_then_report_uncertainty() -> None:
        nonlocal calls
        calls += 1
        real_audit_close()
        raise audit_failure

    monkeypatch.setattr(runtime._executor, "aclose", drain_then_drift)
    monkeypatch.setattr(runtime._audit_sink, "close", close_then_report_uncertainty)

    with pytest.raises(RuntimeCloseUncertain) as caught:
        asyncio.run(runtime.aclose(timeout=1))
    assert isinstance(caught.value.primary_error, RuntimeClosed)
    assert caught.value.cleanup_errors == (audit_failure,)
    assert calls == 1
    with pytest.raises(OSError):
        os.fstat(root_fd)
    os.fstat(project_fd)
    os.fstat(audit_host_fd)
    os.close(project_fd)
    os.close(audit_host_fd)


# RS0_F5_INDEPENDENT_REVIEW_RED_20260909
@pytest.mark.parametrize(
    "drift", ["mode", "inheritable", "dup2", "external-close"]
)
def test_final_root_attestation_after_drain_is_sticky_uncertainty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, drift: str
) -> None:
    _project, project_fd, audit_fd, runtime = create_runtime(tmp_path)
    root_fd = runtime.root_fd
    original_mode = stat.S_IMODE(os.fstat(root_fd).st_mode)
    replacement_fd = -1
    real_drain = runtime._executor.aclose

    async def drain_then_drift(*, timeout: float) -> None:
        nonlocal replacement_fd
        await real_drain(timeout=timeout)
        if drift == "mode":
            os.fchmod(root_fd, original_mode | 0o020)
        elif drift == "inheritable":
            os.set_inheritable(root_fd, True)
        elif drift == "dup2":
            replacement = tmp_path / "post-drain-replacement-root"
            replacement.mkdir()
            replacement_fd = os.open(
                replacement, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
            )
            os.dup2(replacement_fd, root_fd, inheritable=False)
        else:
            os.close(root_fd)

    monkeypatch.setattr(runtime._executor, "aclose", drain_then_drift)
    with pytest.raises(RuntimeCloseUncertain) as first:
        asyncio.run(runtime.aclose(timeout=1))
    assert isinstance(first.value.primary_error, RuntimeClosed)
    with pytest.raises(RuntimeCloseUncertain) as second:
        asyncio.run(runtime.aclose(timeout=1))
    assert second.value is first.value

    with pytest.raises(OSError):
        os.fstat(root_fd)
    os.fstat(project_fd)
    os.fstat(audit_fd)
    os.close(project_fd)
    os.close(audit_fd)
    if replacement_fd >= 0:
        os.close(replacement_fd)


# RS0_F4_INDEPENDENT_REVIEW_RED_20260909
@pytest.mark.parametrize("drift", ["mode", "inheritable", "dup2"])
def test_resolve_binding_attests_live_root_and_stickily_revokes(
    tmp_path: Path, drift: str
) -> None:
    _project, project_fd, audit_fd, runtime = create_runtime(tmp_path)
    caller = ReadCaller(
        SUBJECT, CLIENT, RESOURCE, ("workbench.read",), NOW + 60
    )
    replacement_fd = -1
    original_mode = stat.S_IMODE(os.fstat(runtime.root_fd).st_mode)
    if drift == "mode":
        os.fchmod(runtime.root_fd, original_mode | 0o020)
    elif drift == "inheritable":
        os.set_inheritable(runtime.root_fd, True)
    else:
        replacement = tmp_path / "binding-replacement-root"
        replacement.mkdir()
        replacement_fd = os.open(
            replacement, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
        )
        os.dup2(replacement_fd, runtime.root_fd, inheritable=False)

    assert runtime.resolve_binding(caller, PROJECT) is None

    if drift == "mode":
        os.fchmod(runtime.root_fd, original_mode)
    elif drift == "inheritable":
        os.set_inheritable(runtime.root_fd, False)
    else:
        os.dup2(project_fd, runtime.root_fd, inheritable=False)
    assert runtime.resolve_binding(caller, PROJECT) is None

    asyncio.run(runtime.aclose(timeout=1))
    os.close(project_fd)
    os.close(audit_fd)
    if replacement_fd >= 0:
        os.close(replacement_fd)


# RS0_ROOT_CONTINUITY_REDS_20260909
@pytest.mark.parametrize("drift", ["mode", "inheritable", "dup2"])
def test_owned_root_drift_before_worker_entry_irreversibly_revokes(
    tmp_path: Path, drift: str
) -> None:
    project, project_fd, audit_fd, runtime = create_runtime(tmp_path)
    replacement_fd = -1
    if drift == "mode":
        current_mode = stat.S_IMODE(os.fstat(runtime.root_fd).st_mode)
        os.fchmod(runtime.root_fd, current_mode | 0o020)
    elif drift == "inheritable":
        os.set_inheritable(runtime.root_fd, True)
    else:
        replacement = tmp_path / "replacement-root"
        replacement.mkdir()
        replacement_fd = os.open(
            replacement, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
        )
        os.dup2(replacement_fd, runtime.root_fd, inheritable=False)

    with pytest.raises(RuntimeClosed):
        asyncio.run(runtime.run_io(lambda: "must-not-return"))
    caller = ReadCaller(SUBJECT, CLIENT, RESOURCE, ("workbench.read",), NOW + 60)
    assert runtime.resolve_binding(caller, PROJECT) is None
    with pytest.raises(RuntimeClosed):
        asyncio.run(runtime.run_io(lambda: "must-never-recover"))
    with pytest.raises(RuntimeCloseUncertain):
        asyncio.run(runtime.aclose(timeout=1))
    os.fstat(project_fd)
    os.fstat(audit_fd)
    os.close(project_fd)
    os.close(audit_fd)
    if replacement_fd >= 0:
        os.close(replacement_fd)
    assert project.exists()


@pytest.mark.parametrize("drift", ["mode", "inheritable"])
def test_owned_root_drift_during_physical_work_withholds_result(
    tmp_path: Path, drift: str
) -> None:
    _project, project_fd, audit_fd, runtime = create_runtime(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    def operation() -> str:
        entered.set()
        if not release.wait(5):
            raise AssertionError("root drift gate was not released")
        return "must-not-return"

    async def scenario() -> None:
        pending = asyncio.create_task(runtime.run_io(operation))
        assert await asyncio.to_thread(entered.wait, 1)
        if drift == "mode":
            mode = stat.S_IMODE(os.fstat(runtime.root_fd).st_mode)
            os.fchmod(runtime.root_fd, mode | 0o020)
        else:
            os.set_inheritable(runtime.root_fd, True)
        release.set()
        with pytest.raises(RuntimeClosed):
            await pending
        with pytest.raises(RuntimeCloseUncertain):
            await runtime.aclose(timeout=1)

    asyncio.run(scenario())
    os.close(project_fd)
    os.close(audit_fd)


def test_revoke_while_waiting_for_physical_entry_never_runs_queued_operation(
    tmp_path: Path,
) -> None:
    _project, project_fd, audit_fd, runtime = create_runtime(tmp_path)
    first_entered = threading.Event()
    first_release = threading.Event()
    queued_entered = threading.Event()

    def first() -> str:
        first_entered.set()
        if not first_release.wait(5):
            raise AssertionError("first operation was not released")
        return "first"

    def queued() -> str:
        queued_entered.set()
        return "queued"

    async def scenario() -> None:
        first_task = asyncio.create_task(runtime.run_io(first))
        assert await asyncio.to_thread(first_entered.wait, 1)
        queued_task = asyncio.create_task(runtime.run_io(queued))
        await asyncio.sleep(0.02)
        runtime.revoke()
        first_release.set()
        results = await asyncio.gather(first_task, queued_task, return_exceptions=True)
        assert isinstance(results[1], RuntimeClosed)
        assert not queued_entered.is_set()
        await runtime.aclose(timeout=1)

    asyncio.run(scenario())
    os.close(project_fd)
    os.close(audit_fd)


def test_root_drift_postcheck_outranks_operation_failure(tmp_path: Path) -> None:
    _project, project_fd, audit_fd, runtime = create_runtime(tmp_path)

    def operation() -> None:
        mode = stat.S_IMODE(os.fstat(runtime.root_fd).st_mode)
        os.fchmod(runtime.root_fd, mode | 0o020)
        raise ValueError("operation failure must not hide root drift")

    with pytest.raises(RuntimeClosed):
        asyncio.run(runtime.run_io(operation))
    with pytest.raises(RuntimeCloseUncertain):
        asyncio.run(runtime.aclose(timeout=1))
    os.close(project_fd)
    os.close(audit_fd)


def test_stable_lease_expiry_after_observation_before_await_release_withholds_content(
    tmp_path: Path,
) -> None:
    from contextlib import ExitStack

    current_ms = [NOW * 1000]
    selected_policy = policy()
    with ExitStack() as host_cleanup:
        _project, project_fd, audit_fd = open_dirs(tmp_path)
        # LIFO callbacks preserve the original project-then-audit close order;
        # both are attempted even if the first raises. Exception context is kept.
        host_cleanup.callback(os.close, audit_fd)
        host_cleanup.callback(os.close, project_fd)
        with asyncio.Runner() as runner:
            runtime = WorkbenchReadRuntime.open(
                authenticator=authenticator(selected_policy),
                policy=selected_policy,
                now=lambda: NOW,
                clock_ms=lambda: current_ms[0],
                project_directory_fd=project_fd,
                audit_directory_fd=audit_fd,
                lease=lease(lease_expires_at_ms=NOW * 1000 + 1_000),
                allowed_hosts=("127.0.0.1",),
                max_concurrency=1,
                io_timeout_seconds=1,
            )
            try:
                caller = ReadCaller(
                    SUBJECT, CLIENT, RESOURCE, ("workbench.read",), NOW + 60
                )
                observed = asyncio.Event()
                release = asyncio.Event()

                async def gated_run_io(operation):
                    result = await runtime.run_io(operation)
                    observed.set()
                    await release.wait()
                    return result

                read = create_descriptor_read_port(
                    resolve_binding=runtime.resolve_binding,
                    clock_ms=lambda: current_ms[0],
                    run_io=gated_run_io,
                )

                async def scenario() -> None:
                    pending = asyncio.create_task(
                        read(
                            caller,
                            {"project_ref": PROJECT, "relative_path": "source.txt"},
                        )
                    )
                    try:
                        await asyncio.wait_for(observed.wait(), 1)
                        current_ms[0] = NOW * 1000 + 1_000
                        release.set()
                        with pytest.raises(ProjectReadRefused):
                            await pending
                        # An expired immutable lease cannot revive on clock rewind.
                        current_ms[0] = NOW * 1000
                        with pytest.raises(ProjectReadRefused):
                            await read(
                                caller,
                                {"project_ref": PROJECT, "relative_path": "source.txt"},
                            )
                    finally:
                        release.set()
                        # Only this test's registered async read is settled here.
                        # Cancelling it does not claim to interrupt physical I/O.
                        if not pending.done():
                            pending.cancel()
                        await asyncio.gather(pending, return_exceptions=True)

                runner.run(scenario())
            finally:
                # Still the SAME live loop/context, even after an assertion failure.
                # Actual physical drain remains Runtime's responsibility. The fixed
                # existing timeout is unchanged; a refusal is not hidden or retried.
                runner.run(runtime.aclose(timeout=1))



async def _rs0_one_call_lifetime(
    active_runtime,
    project_root: Path,
    *,
    bearer_token: str,
    mutate,
    events: list,
    observed: threading.Event,
    gate_final: threading.Event,
    release_final: threading.Event,
    state: dict,
    fail_at: str | None = None,
    close_runtime: bool = False,
    caller_fds: tuple[int, ...] = (),
    force_duplicate_fd_close: bool = False,
    inject_runtime_close: bool = False,
    invocation_id: object | None = None,
) -> tuple[object | None, dict]:
    """Shared RS0 fixture lifetime used by gated cases and bounded fault injection.

    Fresh public create_deployment per separately entered lifespan (T1).
    Registers pending before fallible gate/mutation waits; settles every
    registered request (including done) inside the client context; lifespan
    settlement is unconditional. Optional Runtime/FD close runs through this
    same helper so cleanup proof cannot pass if real cleanup is removed.

    R5: publish settlement on raised and returned paths; capture body primary
    before independent cleanup; cleanup-only fails when no primary; inject one
    FD-close failure then still attempt the other FD; Runtime-close inject at
    the real aclose boundary with call evidence.
    """
    # Clear stale last-success receipt before this invocation.
    # R7-LOCAL-1: stamp per-invocation id so recovery cannot adopt a prior receipt.
    bound_invocation_id = invocation_id if invocation_id is not None else object()
    _rs0_one_call_lifetime.last_settlement = {}  # type: ignore[attr-defined]
    events.clear()
    observed.clear()
    gate_final.clear()
    release_final.clear()
    state["tools_call"] = False
    state["final_key_calls"] = 0
    state["resolve_during_tools"] = 0
    _create_deployment = __import__(
        "integrations.workbench_read_mcp.deployment", fromlist=["create_deployment"]
    ).create_deployment
    server = _create_deployment(active_runtime.services)
    app = server.streamable_http_app()
    ready, stop = asyncio.Event(), asyncio.Event()
    life: asyncio.Task | None = None
    pending: asyncio.Task | None = None
    client: httpx.AsyncClient | None = None
    local_cleanup: list[BaseException] = []
    settlement_note: dict = {
        "_invocation_id": bound_invocation_id,
        "request_settled": False,
        "lifespan_settled": False,
        "pending_outcomes": (),
        "requests_registered": 0,
        "no_request_owed": False,
        "runtime_close_attempted": False,
        "runtime_close_called": False,
        "runtime_close_ok": None,
        "runtime_close_error": None,
        "runtime_close_witness_count": 0,
        "runtime_physically_closed": None,
        "fd_attempts": (),
        "successfully_closed_fds": (),
        "fd_dispositions": (),
        "final_fd_outcomes": (),
        "cleanup_errors": (),
        "body_error": None,
    }
    body: object | None = None
    body_error: BaseException | None = None
    fd_attempts: list[tuple] = []
    successfully_closed: list[int] = []
    fd_dispositions: list[tuple] = []
    inject_close = inject_runtime_close or (fail_at == "runtime_close")

    async def lifespan() -> None:
        async with app.router.lifespan_context(app):
            ready.set()
            await stop.wait()

    try:
        # Register lifespan under its cleanup try before readiness wait.
        life = asyncio.create_task(lifespan())
        if fail_at == "readiness":
            raise RuntimeError("INJECTED_READINESS_FAILURE")
        await asyncio.wait_for(ready.wait(), 5)
        headers = {
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-03-26",
        }
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1",
        )
        try:
            async def rpc(method: str, params: dict):
                return await client.post(
                    "/mcp",
                    headers={
                        **headers,
                        "Authorization": "Bearer " + bearer_token,
                    },
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": method,
                        "params": params,
                    },
                )

            hello = await rpc(
                "initialize",
                {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "s1-gate", "version": "1"},
                },
            )
            assert hello.status_code == 200, hello.text
            await rpc("tools/list", {})
            state["tools_call"] = True
            arguments = {
                "project_ref": PROJECT,
                "relative_path": "source.txt",
                "line_count": 1,
                "expected_sha256": hashlib.sha256(
                    (project_root / "source.txt").read_bytes()
                ).hexdigest(),
            }
            # Register pending BEFORE any failing gate/mutation wait.
            pending = asyncio.create_task(
                rpc(
                    "tools/call",
                    {"name": "read_project_file", "arguments": arguments},
                )
            )
            settlement_note["requests_registered"] = 1
            if fail_at == "gate":
                raise RuntimeError("INJECTED_GATE_FAILURE")
            if fail_at == "body_primary":
                raise RuntimeError("INJECTED_PRIMARY_FAILURE")
            assert await asyncio.to_thread(gate_final.wait, 5)
            assert observed.is_set()
            assert "observation_complete" in events
            assert "final_key_entry" in events
            if fail_at == "mutation":
                raise RuntimeError("INJECTED_MUTATION_FAILURE")
            mutate()
            events.append("mutation")
            release_final.set()
            response = await pending
            # Keep pending set so inner finally still gathers the done task.
            assert "release_resumption" in events
            assert "final_revalidation" in events, events
            assert state["final_key_calls"] >= 2
            assert events.index("observation_complete") < events.index(
                "final_key_entry"
            )
            assert events.index("final_key_entry") < events.index("mutation")
            assert events.index("mutation") < events.index("release_resumption")
            assert events.index("release_resumption") < events.index(
                "final_revalidation"
            )
            body = response.json()["result"]
        except BaseException as error:
            # Capture body primary BEFORE client close / independent cleanup.
            body_error = error
        finally:
            # Request settlement INSIDE active client context (before aclose).
            release_final.set()
            if pending is not None:
                owned = pending
                pending = None
                if not owned.done():
                    owned.cancel()
                # Consume every registered outcome including already-done.
                settled = await asyncio.gather(owned, return_exceptions=True)
                settlement_note["pending_outcomes"] = tuple(settled)
                settlement_note["request_settled"] = True
                for item in settled:
                    if isinstance(item, BaseException) and not isinstance(
                        item, asyncio.CancelledError
                    ):
                        local_cleanup.append(item)
            # else: leave request_settled False until vacuous settle below
    except BaseException as error:
        if body_error is None:
            body_error = error
        elif error is not body_error:
            local_cleanup.append(error)
    finally:
        # Independent client close — cleanup, never replaces body primary.
        if client is not None:
            try:
                await client.aclose()
            except BaseException as error:
                local_cleanup.append(error)
        # Lifespan settlement; always release gate.
        release_final.set()
        stop.set()
        if life is not None:
            try:
                await asyncio.wait_for(life, 5)
                settlement_note["lifespan_settled"] = True
            except BaseException as error:
                local_cleanup.append(error)
                # done()/nonempty error list is NOT successful physical settlement.
                settlement_note["lifespan_settled"] = False
        else:
            settlement_note["lifespan_settled"] = True
        # No registered request => vacuously settled / no request owed.
        if settlement_note["requests_registered"] == 0:
            settlement_note["no_request_owed"] = True
            settlement_note["request_settled"] = True
            settlement_note["pending_outcomes"] = ()
        # Optional Runtime physical close through THIS helper at real aclose.
        if close_runtime:
            settlement_note["runtime_close_attempted"] = True
            original_aclose = active_runtime.aclose
            try:
                if inject_close:
                    async def _injected_aclose(*, timeout: float):
                        settlement_note["runtime_close_called"] = True
                        settlement_note["runtime_close_witness_count"] = (
                            int(settlement_note.get("runtime_close_witness_count") or 0)
                            + 1
                        )
                        raise RuntimeError("INJECTED_RUNTIME_CLOSE_FAILURE")

                    active_runtime.aclose = _injected_aclose  # type: ignore[method-assign]
                    try:
                        await active_runtime.aclose(timeout=1)
                    finally:
                        active_runtime.aclose = original_aclose  # type: ignore[method-assign]
                else:
                    # Independent witness: flags/count advance only inside the
                    # delegated original aclose. Deleting this await must fail
                    # the successful-close control (R5-LOCAL-2).
                    async def _witnessed_aclose(*, timeout: float):
                        settlement_note["runtime_close_called"] = True
                        settlement_note["runtime_close_witness_count"] = (
                            int(settlement_note.get("runtime_close_witness_count") or 0)
                            + 1
                        )
                        await original_aclose(timeout=timeout)

                    active_runtime.aclose = _witnessed_aclose  # type: ignore[method-assign]
                    try:
                        await active_runtime.aclose(timeout=1)
                        settlement_note["runtime_close_ok"] = True
                        settlement_note["runtime_physically_closed"] = bool(
                            getattr(active_runtime, "_closed", False)
                        )
                    finally:
                        active_runtime.aclose = original_aclose  # type: ignore[method-assign]
            except BaseException as error:
                settlement_note["runtime_close_ok"] = False
                settlement_note["runtime_close_error"] = error
                settlement_note["runtime_physically_closed"] = bool(
                    getattr(active_runtime, "_closed", False)
                )
                if not settlement_note["runtime_close_called"]:
                    # Entered the close site even if wrapper failed before flag.
                    settlement_note["runtime_close_called"] = True
                local_cleanup.append(error)
        # Optional caller-FD close: inject ONE failure, still attempt other FDs.
        if caller_fds:
            injected_fd_once = False
            for fd in caller_fds:
                try:
                    if fail_at == "fd_close" and not injected_fd_once:
                        injected_fd_once = True
                        raise OSError(9, "INJECTED_FD_CLOSE_FAILURE")
                    os.close(fd)
                    successfully_closed.append(fd)
                    fd_attempts.append((fd, "ok", None))
                    fd_dispositions.append((fd, "closed"))
                    if force_duplicate_fd_close:
                        # Expected duplicate only with prior successful-close evidence.
                        try:
                            os.close(fd)
                            fd_attempts.append((fd, "unexpected_second_ok", None))
                        except BaseException as dup_error:
                            errno = getattr(dup_error, "errno", None)
                            fd_attempts.append((fd, "duplicate_error", errno))
                            # Duplicate after proven successful close is expected.
                            if not (
                                isinstance(dup_error, OSError)
                                and errno == 9
                                and fd in successfully_closed
                            ):
                                local_cleanup.append(dup_error)
                except BaseException as error:
                    errno = getattr(error, "errno", None)
                    fd_attempts.append((fd, "error", errno))
                    # First-close EBADF / injected failure is a real cleanup failure.
                    local_cleanup.append(error)
                    if (
                        fail_at == "fd_close"
                        and isinstance(error, OSError)
                        and "INJECTED_FD_CLOSE_FAILURE" in str(error)
                    ):
                        # Explicit unresolved ownership — do not blindly retry close.
                        fd_dispositions.append((fd, "unresolved_injected_failure"))
                    else:
                        fd_dispositions.append((fd, "error"))
        settlement_note["fd_attempts"] = tuple(fd_attempts)
        settlement_note["successfully_closed_fds"] = tuple(successfully_closed)
        settlement_note["fd_dispositions"] = tuple(fd_dispositions)
        settlement_note["cleanup_errors"] = tuple(local_cleanup)
        settlement_note["body_error"] = body_error
        # Publish for raised AND returned paths (same receipt; no stale reuse).
        _rs0_one_call_lifetime.last_settlement = dict(settlement_note)  # type: ignore[attr-defined]

    if body_error is not None:
        # Preserve exact body primary; cleanup already recorded independently.
        if local_cleanup:
            try:
                body_error.add_note(
                    "cleanup_errors="
                    + ",".join(
                        f"{type(err).__name__}:{err!r}" for err in local_cleanup
                    )
                )
            except Exception:
                pass
        raise body_error
    if local_cleanup:
        # Cleanup-only failure when no primary.
        raise AssertionError(
            "cleanup_only_failures="
            + ",".join(f"{type(err).__name__}:{err!r}" for err in local_cleanup)
        )
    return body, settlement_note


def test_final_key_for_gate_after_observation_withholds_on_lease_expiry_and_revoke(
    tmp_path: Path,
) -> None:
    """S1 gated-key-provider regression on the real Runtime→app→verifier path.

    Gate key_for only during the FINAL post-observation verify_token. While held:
    advance clock_ms to EXACT lease expiry (JWT still valid), then on a separate
    fresh lifetime revoke the same binding. Release the original key. Require
    sanitized refusal and no buffered file content. Positive control returns the
    attributed observation. Assert the final check ran after key lookup resumed.

    R1: pending is registered before any failing wait; gate release + cancel-and-
    gather happen while client/lifespan remain valid; Runtime closes inside its
    owning async lifetime; FD cleanup attempts retain primary+cleanup errors.
    Compact injected readiness/gate/mutation/cleanup discriminators are included.
    R2: ordered recorder covers port completion, final-key entry, mutation,
    release/resumption, and synchronous final revalidation.
    """
    signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    public.update(kid="runtime-key", alg="RS256", use="sig")
    selected_policy = policy()
    project, project_fd, audit_fd = open_dirs(tmp_path)
    start = int(time.time())
    lease_deadline_ms = (start + 600) * 1000
    # T1: construct/open strictly before deadline; equality is exercised later.
    jwt_now = [start]
    lease_ms = [lease_deadline_ms - 1]
    observed = threading.Event()
    gate_final = threading.Event()
    release_final = threading.Event()
    state = {"tools_call": False, "final_key_calls": 0, "resolve_during_tools": 0}
    events: list[str] = []
    runtime = None
    runtime2 = None
    project_fd2 = None
    audit_fd2 = None
    original_observe = read_port_module.observe_file
    primary_error: BaseException | None = None
    cleanup_errors: list[BaseException] = []

    class GatedKeys(Keys):
        async def key_for(self, kid: str):
            value = await super().key_for(kid)
            if not state["tools_call"]:
                return value
            state["final_key_calls"] += 1
            if state["final_key_calls"] == 2:
                assert await asyncio.to_thread(observed.wait, 5), (
                    "observation/port return missing before final key_for"
                )
                events.append("final_key_entry")
                gate_final.set()
                # T4: yield the event loop while waiting for mutate/release.
                assert await asyncio.to_thread(release_final.wait, 5), (
                    "final key_for gate not released"
                )
                events.append("release_resumption")
            return value

    def witnessing_observe(*args, **kwargs):
        # T3: patch the read_port binding actually invoked by the port.
        result = original_observe(*args, **kwargs)
        events.append("observation_complete")
        observed.set()
        return result

    read_port_module.observe_file = witnessing_observe  # type: ignore[assignment]
    try:
        auth = JwtAuthenticator(policy=selected_policy, jwks_cache=GatedKeys(public))
        runtime = WorkbenchReadRuntime.open(
            authenticator=auth,
            policy=selected_policy,
            now=lambda: jwt_now[0],
            clock_ms=lambda: lease_ms[0],
            project_directory_fd=project_fd,
            audit_directory_fd=audit_fd,
            lease=lease(lease_expires_at_ms=lease_deadline_ms),
            allowed_hosts=("127.0.0.1",),
            max_concurrency=1,
            io_timeout_seconds=2,
        )
        original_resolve = runtime.resolve_binding

        def recording_resolve(caller, project_ref):
            binding = original_resolve(caller, project_ref)
            if state["tools_call"]:
                state["resolve_during_tools"] += 1
                # After final-key gate resumes, make_final_authorization.revalidate
                # snapshots again — that is the synchronous final fence.
                if (
                    state["final_key_calls"] >= 2
                    and release_final.is_set()
                    and "final_revalidation" not in events
                ):
                    events.append("final_revalidation")
            return binding

        runtime.resolve_binding = recording_resolve  # type: ignore[method-assign]
        # Keep services/deployment resolver view consistent with the wrapper.
        runtime.services = dataclasses.replace(
            runtime.services, resolve_binding=recording_resolve
        )
        runtime.server = __import__(
            "integrations.workbench_read_mcp.deployment", fromlist=["create_deployment"]
        ).create_deployment(runtime.services)

        def token() -> str:
            # T2: lifetime == max_token_lifetime_seconds (3600), not 3601.
            return jwt.encode(
                {
                    "iss": ISSUER,
                    "sub": SUBJECT_RAW,
                    "aud": RESOURCE,
                    "iat": start,
                    "exp": start + 3600,
                    "scope": "workbench.read",
                    "client_id": CLIENT_RAW,
                },
                signing_key,
                algorithm="RS256",
                headers={"kid": "runtime-key"},
            )

        async def one_call(
            active_runtime,
            project_root: Path,
            *,
            mutate,
            fail_at: str | None = None,
            close_runtime: bool = False,
            caller_fds: tuple[int, ...] = (),
            force_duplicate_fd_close: bool = False,
            inject_runtime_close: bool = False,
        ) -> dict:
            # Delegate to the shared fixture lifetime helper (R3-LOCAL-5 / R5 receipt).
            # R7-LOCAL-1: invalidate/bind BEFORE fallible token() preparation.
            inv_id = object()
            one_call.last_settlement = {}  # type: ignore[attr-defined]
            _rs0_one_call_lifetime.last_settlement = {}  # type: ignore[attr-defined]
            bearer_token = token()
            try:
                body, settlement_note = await _rs0_one_call_lifetime(
                    active_runtime,
                    project_root,
                    bearer_token=bearer_token,
                    mutate=mutate,
                    events=events,
                    observed=observed,
                    gate_final=gate_final,
                    release_final=release_final,
                    state=state,
                    fail_at=fail_at,
                    close_runtime=close_runtime,
                    caller_fds=caller_fds,
                    force_duplicate_fd_close=force_duplicate_fd_close,
                    inject_runtime_close=inject_runtime_close,
                    invocation_id=inv_id,
                )
            except BaseException:
                recovered = getattr(_rs0_one_call_lifetime, "last_settlement", {}) or {}
                # Identity match only — do not adopt a prior invocation receipt.
                if (
                    isinstance(recovered, dict)
                    and recovered.get("_invocation_id") is inv_id
                ):
                    settlement_note = dict(recovered)
                else:
                    settlement_note = {"_invocation_id": inv_id}
                one_call.last_settlement = settlement_note  # type: ignore[attr-defined]
                cleanup_errors.extend(settlement_note.get("cleanup_errors") or ())
                raise
            one_call.last_settlement = dict(settlement_note)  # type: ignore[attr-defined]
            cleanup_errors.extend(settlement_note.get("cleanup_errors") or ())
            if body is None and fail_at is None:
                raise AssertionError("one_call returned no body")
            return body  # type: ignore[return-value]

        async def exercise() -> None:
            # Capture body exception BEFORE owning Runtime close (R3-LOCAL-4).
            body_error: BaseException | None = None
            try:
                # Compact readiness / gate / mutation failure-path discriminators
                # against the actual shared helper settlement path.
                for injected in ("readiness", "gate", "mutation"):
                    try:
                        await one_call(
                            runtime, project, mutate=lambda: None, fail_at=injected
                        )
                    except RuntimeError as error:
                        assert f"INJECTED_{injected.upper()}_FAILURE" in str(error)
                        settled = getattr(one_call, "last_settlement", {})
                        assert settled.get("lifespan_settled") is True, settled
                        assert settled.get("request_settled") is True, settled
                        if injected == "readiness":
                            assert settled.get("requests_registered") == 0, settled
                            assert settled.get("no_request_owed") is True, settled
                            assert settled.get("pending_outcomes") == (), settled
                        else:
                            assert settled.get("requests_registered") == 1, settled
                            assert len(settled.get("pending_outcomes") or ()) == 1, settled
                    else:
                        raise AssertionError(f"expected injected {injected} failure")

                body = await one_call(runtime, project, mutate=lambda: None)
                assert body.get("isError") is False, body
                assert body["structuredContent"]["content"] == "runtime source\n"
                assert body["structuredContent"]["project_ref"] == PROJECT
                assert "final_revalidation" in events

                body = await one_call(
                    runtime,
                    project,
                    mutate=lambda: lease_ms.__setitem__(0, lease_deadline_ms),
                )
                assert body.get("isError") is True, body
                dumped = json.dumps(body)
                assert "runtime source" not in dumped
                assert "PRIVATE" not in dumped
                # Intended sanitized refusal code with observation/guard witnesses.
                assert "PROJECT_READ_REFUSED" in dumped, dumped
                assert "observation_complete" in events
                assert "final_key_entry" in events
            except BaseException as error:
                body_error = error
            # Collect Runtime-close errors independently; retain physical uncertainty.
            try:
                await runtime.aclose(timeout=1)
            except BaseException as close_error:
                cleanup_errors.append(close_error)
            if body_error is not None:
                raise body_error

        asyncio.run(exercise())

        # Separate revoke scenario on a fresh runtime lifetime.
        observed.clear()
        gate_final.clear()
        release_final.clear()
        state["tools_call"] = False
        state["final_key_calls"] = 0
        lease_ms[0] = lease_deadline_ms - 1
        project2, project_fd2, audit_fd2 = open_dirs(tmp_path / "revoke")
        auth2 = JwtAuthenticator(policy=selected_policy, jwks_cache=GatedKeys(public))
        runtime2 = WorkbenchReadRuntime.open(
            authenticator=auth2,
            policy=selected_policy,
            now=lambda: jwt_now[0],
            clock_ms=lambda: lease_ms[0],
            project_directory_fd=project_fd2,
            audit_directory_fd=audit_fd2,
            lease=lease(lease_expires_at_ms=lease_deadline_ms),
            allowed_hosts=("127.0.0.1",),
            max_concurrency=1,
            io_timeout_seconds=2,
        )
        original_resolve2 = runtime2.resolve_binding

        def recording_resolve2(caller, project_ref):
            binding = original_resolve2(caller, project_ref)
            if state["tools_call"]:
                if (
                    state["final_key_calls"] >= 2
                    and release_final.is_set()
                    and "final_revalidation" not in events
                ):
                    events.append("final_revalidation")
            return binding

        runtime2.resolve_binding = recording_resolve2  # type: ignore[method-assign]
        runtime2.services = dataclasses.replace(
            runtime2.services, resolve_binding=recording_resolve2
        )
        runtime2.server = __import__(
            "integrations.workbench_read_mcp.deployment", fromlist=["create_deployment"]
        ).create_deployment(runtime2.services)

        async def revoke_case() -> None:
            body_error: BaseException | None = None
            try:
                body = await one_call(
                    runtime2, project2, mutate=lambda: runtime2.revoke()
                )
                assert body.get("isError") is True, body
                dumped = json.dumps(body)
                assert "runtime source" not in dumped
                assert "PRIVATE" not in dumped
                assert "PROJECT_READ_REFUSED" in dumped, dumped
                assert "final_revalidation" in events
                assert "observation_complete" in events
            except BaseException as error:
                body_error = error
            try:
                await runtime2.aclose(timeout=1)
            except BaseException as close_error:
                cleanup_errors.append(close_error)
            if body_error is not None:
                raise body_error

        asyncio.run(revoke_case())

    except BaseException as error:
        primary_error = error
        raise
    finally:
        # T5/R1: release gate, restore patch, settle runtimes, close fds.
        # Attempt every FD cleanup; retain primary and cleanup errors.
        # No blanket EBADF suppression: caller FDs are first-close owned and
        # distinct from Runtime's separately opened root descriptor (R3-LOCAL-4).
        release_final.set()
        read_port_module.observe_file = original_observe  # type: ignore[assignment]
        successfully_closed_fds: set[int] = set()
        for active in (runtime, runtime2):
            if active is None:
                continue
            try:
                # Prefer no second-loop close when already closed in-lifetime;
                # still attempt if a prior failure skipped owning-lifetime close.
                # Physical-close uncertainty is retained (not inferred).
                asyncio.run(active.aclose(timeout=1))
            except BaseException as cleanup_error:
                cleanup_errors.append(cleanup_error)
        for fd in (project_fd2, audit_fd2, project_fd, audit_fd):
            if fd is None:
                continue
            try:
                os.close(fd)
                successfully_closed_fds.add(fd)
            except BaseException as cleanup_error:
                # First-close EBADF is a cleanup failure without prior evidence.
                cleanup_errors.append(cleanup_error)
        # Compact cleanup discriminator: retained errors must not hide primary.
        if primary_error is not None and cleanup_errors:
            try:
                primary_error.add_note(
                    "cleanup_errors="
                    + ",".join(f"{type(err).__name__}:{err!r}" for err in cleanup_errors)
                )
            except Exception:
                pass
        elif primary_error is None and cleanup_errors:
            # Propagate ALL cleanup-only failures (including first-close EBADF).
            # Expected duplicate close requires exact prior successful-close evidence
            # recorded above — not errno filtering alone.
            raise AssertionError(
                "cleanup_only_failures="
                + ",".join(f"{type(err).__name__}:{err!r}" for err in cleanup_errors)
                + f"; successfully_closed_fds={sorted(successfully_closed_fds)}"
            )


def test_injected_cleanup_failure_path_retains_primary_and_cleanup_evidence(
    tmp_path: Path,
) -> None:
    """R3-LOCAL-5: bounded faults through the ACTUAL shared one_call lifetime helper.

    Uses _rs0_one_call_lifetime (same helper as the gated Runtime cases). Injects
    readiness/gate/mutation/Runtime-close/FD-close through that helper. Requires
    registered-task/lifespan outcomes, Runtime physical disposition, each FD
    attempt, cleanup-only failure and primary-plus-cleanup preservation. No
    copied miniature helper that could pass if real cleanup were removed.
    """
    signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    public.update(kid="runtime-key", alg="RS256", use="sig")
    selected_policy = policy()
    project, project_fd, audit_fd = open_dirs(tmp_path)
    start_ts = int(time.time())
    lease_deadline_ms = (start_ts + 600) * 1000
    jwt_now = [start_ts]
    lease_ms = [lease_deadline_ms - 1]
    observed = threading.Event()
    gate_final = threading.Event()
    release_final = threading.Event()
    state = {"tools_call": False, "final_key_calls": 0, "resolve_during_tools": 0}
    events: list[str] = []
    original_observe = read_port_module.observe_file
    primary_error: BaseException | None = None
    cleanup_errors: list[BaseException] = []

    class GatedKeys(Keys):
        async def key_for(self, kid: str):
            value = await super().key_for(kid)
            if not state["tools_call"]:
                return value
            state["final_key_calls"] += 1
            if state["final_key_calls"] == 2:
                assert await asyncio.to_thread(observed.wait, 5)
                events.append("final_key_entry")
                gate_final.set()
                assert await asyncio.to_thread(release_final.wait, 5)
                events.append("release_resumption")
            return value

    def witnessing_observe(*args, **kwargs):
        result = original_observe(*args, **kwargs)
        events.append("observation_complete")
        observed.set()
        return result

    def token() -> str:
        return jwt.encode(
            {
                "iss": ISSUER,
                "sub": SUBJECT_RAW,
                "aud": RESOURCE,
                "iat": start_ts,
                "exp": start_ts + 3600,
                "scope": "workbench.read",
                "client_id": CLIENT_RAW,
            },
            signing_key,
            algorithm="RS256",
            headers={"kid": "runtime-key"},
        )

    read_port_module.observe_file = witnessing_observe  # type: ignore[assignment]
    runtime = None
    try:
        auth = JwtAuthenticator(policy=selected_policy, jwks_cache=GatedKeys(public))
        runtime = WorkbenchReadRuntime.open(
            authenticator=auth,
            policy=selected_policy,
            now=lambda: jwt_now[0],
            clock_ms=lambda: lease_ms[0],
            project_directory_fd=project_fd,
            audit_directory_fd=audit_fd,
            lease=lease(lease_expires_at_ms=lease_deadline_ms),
            allowed_hosts=("127.0.0.1",),
            max_concurrency=1,
            io_timeout_seconds=2,
        )
        original_resolve = runtime.resolve_binding

        def recording_resolve(caller, project_ref):
            binding = original_resolve(caller, project_ref)
            if state["tools_call"]:
                state["resolve_during_tools"] += 1
                if (
                    state["final_key_calls"] >= 2
                    and release_final.is_set()
                    and "final_revalidation" not in events
                ):
                    events.append("final_revalidation")
            return binding

        runtime.resolve_binding = recording_resolve  # type: ignore[method-assign]
        runtime.services = dataclasses.replace(
            runtime.services, resolve_binding=recording_resolve
        )
        runtime.server = __import__(
            "integrations.workbench_read_mcp.deployment", fromlist=["create_deployment"]
        ).create_deployment(runtime.services)

        async def call_helper(
            fail_at: str | None = None,
            *,
            mutate=None,
            close_runtime: bool = False,
            caller_fds: tuple[int, ...] = (),
            force_duplicate_fd_close: bool = False,
            inject_runtime_close: bool = False,
        ):
            # R7-LOCAL-1: bind/invalidate BEFORE fallible token() preparation.
            inv_id = object()
            _rs0_one_call_lifetime.last_settlement = {}  # type: ignore[attr-defined]
            bearer_token = token()
            return await _rs0_one_call_lifetime(
                runtime,
                project,
                bearer_token=bearer_token,
                mutate=mutate or (lambda: None),
                events=events,
                observed=observed,
                gate_final=gate_final,
                release_final=release_final,
                state=state,
                fail_at=fail_at,
                close_runtime=close_runtime,
                caller_fds=caller_fds,
                force_duplicate_fd_close=force_duplicate_fd_close,
                inject_runtime_close=inject_runtime_close,
                invocation_id=inv_id,
            )

        def _recover_invocation_receipt(note: dict) -> dict:
            """R6-LOCAL-1 / R7-LOCAL-1: recover only a receipt for THIS invocation.

            Bind/invalidate happens before fallible token() preparation. Recovery
            requires identity match on _invocation_id. Absence of a matching
            current receipt retains fresh caller ownership of newly opened FDs
            (including when the OS reuses FD numbers after a prior close).
            Entered-helper raised paths still recover their published receipt.
            Genuine prior close-error no-retry remains in _owner_finalize_fds.
            """
            recovered = getattr(_rs0_one_call_lifetime, "last_settlement", None)
            if not isinstance(recovered, dict) or not recovered:
                return note
            expected = note.get("_invocation_id")
            if expected is None:
                # No current invocation bound — do not adopt a foreign/prior
                # settlement (would suppress close of reused FD numbers).
                return note
            if recovered.get("_invocation_id") is not expected:
                return note
            note.update(recovered)
            return note

        def _owner_finalize_fds(
            owned_fds: list[int],
            settlement: dict,
            *,
            allow_first_close_of_unresolved: bool = True,
        ) -> dict[int, str]:
            """R5-LOCAL-1 / R6-LOCAL-1: independently attempt each owned FD cleanup.

            - Suppress duplicate only with exact earlier successful-close evidence
              (successfully_closed_fds or disposition "closed").
            - Known-before-close injection permits one actual first close.
            - Genuine prior close error ("error") retains uncertainty — no retry.
            - First close only for never-attempted owned FDs or allowed injection.
            - Record final physical outcomes; propagate unexpected errors.
            - Independent sibling outcomes/primary errors remain recorded.
            """
            closed_ok = set(settlement.get("successfully_closed_fds") or ())
            prior_disp = dict(settlement.get("fd_dispositions") or ())
            finals: dict[int, str] = {}
            for fd in list(owned_fds):
                prior = prior_disp.get(fd)
                if fd in closed_ok or prior == "closed":
                    finals[fd] = "suppressed_duplicate_prior_success"
                    continue
                # Genuine prior close failure: retain uncertainty without replay.
                if prior == "error":
                    finals[fd] = "retained_prior_close_error_no_retry"
                    continue
                if prior == "unresolved_injected_failure" and not allow_first_close_of_unresolved:
                    finals[fd] = "retained_unresolved_no_retry"
                    continue
                # First close: never-attempted owned FD, or explicitly proven
                # before-close injection when allow_first_close_of_unresolved.
                try:
                    os.close(fd)
                    finals[fd] = "owner_closed"
                    if prior == "unresolved_injected_failure":
                        prior_disp[fd] = "owner_closed_after_injected_skip"
                except OSError as err:
                    finals[fd] = f"owner_close_error:{getattr(err, 'errno', None)}"
                    cleanup_errors.append(err)
                    if prior == "unresolved_injected_failure":
                        prior_disp[fd] = "owner_close_failed_after_injected_skip"
                    # Do not retry after this failed first/owner attempt.
            settlement["fd_dispositions"] = tuple(prior_disp.items())
            settlement["final_fd_outcomes"] = tuple(finals.items())
            return finals

        def _require_exact_cleanup(
            note: dict,
            *,
            expected_substrings: tuple[str, ...] = (),
            allow_empty: bool = False,
        ) -> None:
            """R5-LOCAL-3: exact cleanup set; reject every extra failure."""
            errors = tuple(note.get("cleanup_errors") or ())
            if allow_empty:
                if errors:
                    cleanup_errors.extend(errors)
                    raise AssertionError(
                        "unexpected_cleanup_errors="
                        + ",".join(f"{type(e).__name__}:{e!r}" for e in errors)
                    )
                return
            if len(errors) != len(expected_substrings):
                cleanup_errors.extend(errors)
                raise AssertionError(
                    "cleanup_error_set_mismatch="
                    + ",".join(f"{type(e).__name__}:{e!r}" for e in errors)
                    + f"; expected_substrings={expected_substrings!r}"
                )
            for err, needle in zip(errors, expected_substrings):
                if needle not in str(err):
                    cleanup_errors.extend(errors)
                    raise AssertionError(
                        "cleanup_error_content_mismatch="
                        + f"{err!r} missing {needle!r}"
                    )

        async def via_actual_helper() -> None:
            # readiness: zero registrations / vacuous settle / lifespan settled
            try:
                await call_helper(fail_at="readiness")
            except RuntimeError as error:
                assert "INJECTED_READINESS_FAILURE" in str(error)
                note = getattr(_rs0_one_call_lifetime, "last_settlement", {})
                assert note.get("lifespan_settled") is True, note
                assert note.get("request_settled") is True, note
                assert note.get("requests_registered") == 0, note
                assert note.get("no_request_owed") is True, note
                assert note.get("pending_outcomes") == (), note
                assert note.get("body_error") is error, (note, error)
                _require_exact_cleanup(note, allow_empty=True)
            else:
                raise AssertionError("expected readiness failure via actual helper")

            # gate: one registered + settled outcome
            try:
                await call_helper(fail_at="gate")
            except RuntimeError as error:
                assert "INJECTED_GATE_FAILURE" in str(error)
                note = getattr(_rs0_one_call_lifetime, "last_settlement", {})
                assert note.get("lifespan_settled") is True, note
                assert note.get("request_settled") is True, note
                assert note.get("requests_registered") == 1, note
                assert len(note.get("pending_outcomes") or ()) == 1, note
                assert note.get("body_error") is error, (note, error)
                _require_exact_cleanup(note, allow_empty=True)
            else:
                raise AssertionError("expected gate failure via actual helper")

            # mutation: one registered + settled outcome
            try:
                await call_helper(fail_at="mutation")
            except RuntimeError as error:
                assert "INJECTED_MUTATION_FAILURE" in str(error)
                note = getattr(_rs0_one_call_lifetime, "last_settlement", {})
                assert note.get("lifespan_settled") is True, note
                assert note.get("request_settled") is True, note
                assert note.get("requests_registered") == 1, note
                assert len(note.get("pending_outcomes") or ()) == 1, note
                assert note.get("body_error") is error, (note, error)
                _require_exact_cleanup(note, allow_empty=True)
            else:
                raise AssertionError("expected mutation failure via actual helper")

            # Successful same-helper Runtime-close control on a disposable runtime.
            # Independent witness + physical closed postcondition (R5-LOCAL-2).
            # R6-LOCAL-2/3: persistent receipt, custody before fallible asserts,
            # and physical Runtime-owned audit FD disposition (not caller ctrl_audit).
            # Closing caller FDs is NOT Runtime-owned root/audit closure.
            ctrl_project, ctrl_fd, ctrl_audit = open_dirs(tmp_path / "close-control")
            ctrl_owned = [ctrl_fd, ctrl_audit]
            ctrl_runtime = None
            # One persistent receipt — never replaced by a temporary dict.
            ctrl_inv = object()
            ctrl_note: dict = {
                "_invocation_id": ctrl_inv,
                "successfully_closed_fds": (),
                "fd_dispositions": (),
                "final_fd_outcomes": (),
                "cleanup_errors": (),
                "body_error": None,
                "runtime_custody": None,
                "root_fd_ebadf": None,
                "audit_fds_ebadf": None,
            }
            ctrl_close_ok = False
            ctrl_primary: BaseException | None = None
            ctrl_owned_audit_fd: int | None = None
            ctrl_owned_directory_fd: int | None = None
            try:
                ctrl_auth = JwtAuthenticator(
                    policy=selected_policy, jwks_cache=GatedKeys(public)
                )
                ctrl_runtime = WorkbenchReadRuntime.open(
                    authenticator=ctrl_auth,
                    policy=selected_policy,
                    now=lambda: jwt_now[0],
                    clock_ms=lambda: lease_ms[0],
                    project_directory_fd=ctrl_fd,
                    audit_directory_fd=ctrl_audit,
                    lease=lease(lease_expires_at_ms=lease_deadline_ms),
                    allowed_hosts=("127.0.0.1",),
                    max_concurrency=1,
                    io_timeout_seconds=2,
                )
                # R6-LOCAL-3: capture Runtime-owned audit sink FDs BEFORE close.
                # Caller ctrl_audit is a separate host directory FD.
                ctrl_owned_audit_fd = ctrl_runtime._audit_sink._audit_fd
                ctrl_owned_directory_fd = ctrl_runtime._audit_sink._directory_fd
                ctrl_note["captured_runtime_audit_fd"] = ctrl_owned_audit_fd
                ctrl_note["captured_runtime_directory_fd"] = ctrl_owned_directory_fd
                # R7-LOCAL-1: invalidate BEFORE fallible token() preparation.
                _rs0_one_call_lifetime.last_settlement = {}  # type: ignore[attr-defined]
                ctrl_bearer = token()
                try:
                    await _rs0_one_call_lifetime(
                        ctrl_runtime,
                        ctrl_project,
                        bearer_token=ctrl_bearer,
                        mutate=lambda: None,
                        events=events,
                        observed=observed,
                        gate_final=gate_final,
                        release_final=release_final,
                        state=state,
                        fail_at="readiness",
                        close_runtime=True,
                        inject_runtime_close=False,
                        invocation_id=ctrl_inv,
                    )
                except RuntimeError as error:
                    assert "INJECTED_READINESS_FAILURE" in str(error), error
                    _recover_invocation_receipt(ctrl_note)
                    assert ctrl_note.get("runtime_close_attempted") is True, ctrl_note
                    assert ctrl_note.get("runtime_close_called") is True, ctrl_note
                    assert ctrl_note.get("runtime_close_ok") is True, ctrl_note
                    assert ctrl_note.get("runtime_close_witness_count") == 1, ctrl_note
                    assert ctrl_note.get("runtime_physically_closed") is True, ctrl_note
                    assert ctrl_note.get("lifespan_settled") is True, ctrl_note
                    assert ctrl_note.get("runtime_close_error") is None, ctrl_note
                    _require_exact_cleanup(ctrl_note, allow_empty=True)
                    # Independent of helper-written flags: production Runtime closed.
                    assert getattr(ctrl_runtime, "_closed", False) is True, ctrl_runtime
                    # Sticky uncertainty is distinct from successful physical close.
                    assert getattr(ctrl_runtime, "_close_uncertain", None) is None, (
                        ctrl_runtime
                    )
                    try:
                        os.fstat(ctrl_runtime._lease.root_fd)
                    except OSError as root_err:
                        assert getattr(root_err, "errno", None) == 9, root_err
                        ctrl_note["root_fd_ebadf"] = True
                    else:
                        ctrl_note["root_fd_ebadf"] = False
                        raise AssertionError(
                            "runtime-owned root_fd still open after successful close"
                        )
                    # R6-LOCAL-3: physical closed disposition of owned audit FDs.
                    audit_ok = True
                    for label, owned_fd in (
                        ("_audit_fd", ctrl_owned_audit_fd),
                        ("_directory_fd", ctrl_owned_directory_fd),
                    ):
                        try:
                            os.fstat(owned_fd)
                        except OSError as audit_err:
                            assert getattr(audit_err, "errno", None) == 9, (
                                label,
                                audit_err,
                            )
                        else:
                            audit_ok = False
                            raise AssertionError(
                                f"runtime-owned audit {label} still open after "
                                "successful close"
                            )
                    ctrl_note["audit_fds_ebadf"] = audit_ok
                    ctrl_close_ok = True
                    ctrl_note["runtime_custody"] = "physically_closed_settled_no_replay"
                else:
                    raise AssertionError(
                        "expected readiness primary on close-control helper"
                    )
            except BaseException as error:
                # Capture original body/test primary before finalization.
                ctrl_primary = error
                _recover_invocation_receipt(ctrl_note)
                if ctrl_note.get("body_error") is None:
                    ctrl_note["body_error"] = error
                raise
            finally:
                # Caller FDs are distinct from Runtime-owned root/audit.
                _recover_invocation_receipt(ctrl_note)
                _owner_finalize_fds(ctrl_owned, ctrl_note)
                # R6-LOCAL-2 / R7-LOCAL-2: classify runtime custody BEFORE fallible
                # assertions. Carry current-invocation runtime_close_attempted and
                # exact error/physical evidence. Attempted incomplete/error remains
                # unresolved and must NOT replay aclose. _closed alone cannot prove
                # physical settlement after an owned audit/directory FD probe fails.
                if ctrl_runtime is not None and not ctrl_close_ok:
                    sticky = getattr(ctrl_runtime, "_close_uncertain", None)
                    closed_flag = bool(getattr(ctrl_runtime, "_closed", False))
                    attempted = bool(ctrl_note.get("runtime_close_attempted"))
                    close_ok = ctrl_note.get("runtime_close_ok")
                    root_ebadf = ctrl_note.get("root_fd_ebadf")
                    audit_ebadf = ctrl_note.get("audit_fds_ebadf")
                    if attempted and close_ok is not True:
                        # Attempted incomplete/failed close — unresolved, no replay.
                        ctrl_note["runtime_custody"] = (
                            "attempted_incomplete_or_error_no_replay"
                        )
                    elif sticky is not None:
                        ctrl_note["runtime_custody"] = (
                            "sticky_close_uncertain_no_replay"
                        )
                    elif (
                        closed_flag
                        and root_ebadf is True
                        and audit_ebadf is True
                    ):
                        ctrl_note["runtime_custody"] = (
                            "physically_closed_settled_no_replay"
                        )
                    elif closed_flag:
                        # _closed alone is insufficient without physical evidence.
                        ctrl_note["runtime_custody"] = (
                            "closed_flag_insufficient_without_physical_evidence"
                        )
                    elif not attempted:
                        # Proven never-attempted owned Runtime may receive FIRST close.
                        ctrl_note["runtime_custody"] = (
                            "never_attempted_owned_first_close"
                        )
                        try:
                            await ctrl_runtime.aclose(timeout=1)
                            ctrl_note["runtime_custody"] = "owner_first_closed"
                        except BaseException as first_close_err:
                            cleanup_errors.append(first_close_err)
                            ctrl_note["runtime_first_close_error"] = repr(
                                first_close_err
                            )
                            # Preserve original primary — do not convert retry/
                            # first-close result into ownership evidence that
                            # replaces the outward primary.
                    else:
                        # Attempted with close_ok True but control incomplete —
                        # still no aclose replay.
                        ctrl_note["runtime_custody"] = (
                            "attempted_unconfirmed_no_replay"
                        )
                # Fallible post-cleanup assertions after custody classification.
                # If an original primary exists, append assertion failures to
                # cleanup_errors instead of replacing the primary.
                try:
                    assert dict(ctrl_note.get("final_fd_outcomes") or {}), (
                        "close-control must record final caller-FD outcomes"
                    )
                    assert ctrl_note.get("runtime_custody") is not None or ctrl_close_ok, (
                        "close-control must classify runtime custody",
                        ctrl_note,
                    )
                except BaseException as assert_err:
                    if ctrl_primary is not None:
                        cleanup_errors.append(assert_err)
                    else:
                        raise

            # Primary INSIDE helper body + Runtime-close inject at real aclose boundary.
            try:
                await call_helper(
                    fail_at="body_primary",
                    close_runtime=True,
                    inject_runtime_close=True,
                )
            except RuntimeError as error:
                assert "INJECTED_PRIMARY_FAILURE" in str(error), error
                note = getattr(_rs0_one_call_lifetime, "last_settlement", {})
                assert note.get("body_error") is error, (note, error)
                assert note.get("runtime_close_attempted") is True, note
                assert note.get("runtime_close_called") is True, note
                assert note.get("runtime_close_ok") is False, note
                assert note.get("runtime_close_error") is not None, note
                assert "INJECTED_RUNTIME_CLOSE_FAILURE" in str(
                    note.get("runtime_close_error")
                ), note
                assert note.get("lifespan_settled") is True, note
                _require_exact_cleanup(
                    note,
                    expected_substrings=("INJECTED_RUNTIME_CLOSE_FAILURE",),
                )
                assert note.get("runtime_close_error") is (
                    note.get("cleanup_errors") or (None,)
                )[0], note
            else:
                raise AssertionError("primary failure was not raised")

            # FD-close through actual helper; inject one failure, close the other;
            # owning cleanup records final physical disposition (R5-LOCAL-1).
            probe_project, probe_fd, probe_audit = open_dirs(tmp_path / "cleanup-probe")
            probe_owned = [probe_fd, probe_audit]
            probe_inv = object()
            note: dict = {"_invocation_id": probe_inv}
            # R7-LOCAL-1: invalidate BEFORE fallible token() preparation.
            _rs0_one_call_lifetime.last_settlement = {}  # type: ignore[attr-defined]
            try:
                try:
                    probe_bearer = token()
                    _body, returned_note = await _rs0_one_call_lifetime(
                        runtime,
                        probe_project,
                        bearer_token=probe_bearer,
                        mutate=lambda: None,
                        events=events,
                        observed=observed,
                        gate_final=gate_final,
                        release_final=release_final,
                        state=state,
                        fail_at="fd_close",
                        caller_fds=(probe_fd, probe_audit),
                        invocation_id=probe_inv,
                    )
                    note.update(returned_note)
                except AssertionError as error:
                    # cleanup-only path if body succeeded then FD cleanup failed
                    _recover_invocation_receipt(note)
                    assert "cleanup_only_failures" in str(error), error
                    assert note.get("body_error") is None, note
                except BaseException as error:
                    _recover_invocation_receipt(note)
                    cleanup_errors.append(error)
                    raise
                _recover_invocation_receipt(note)
                assert note.get("fd_attempts"), note
                assert len(note.get("fd_attempts") or ()) == 2, note
                dispositions = dict(note.get("fd_dispositions") or ())
                assert len(dispositions) == 2, note
                assert sum(1 for d in dispositions.values() if d == "closed") == 1, note
                assert (
                    sum(
                        1
                        for d in dispositions.values()
                        if d == "unresolved_injected_failure"
                    )
                    == 1
                ), note
                assert note.get("cleanup_errors"), note
                _require_exact_cleanup(
                    note,
                    expected_substrings=("INJECTED_FD_CLOSE_FAILURE",),
                )
                assert any(
                    attempt[1] == "error" for attempt in note.get("fd_attempts") or ()
                ), note
                assert any(
                    attempt[1] == "ok" for attempt in note.get("fd_attempts") or ()
                ), note
            finally:
                _recover_invocation_receipt(note)
                _owner_finalize_fds(probe_owned, note)
            # Assert final dispositions AFTER owning finally (R5-LOCAL-1).
            finals = dict(note.get("final_fd_outcomes") or ())
            assert len(finals) == 2, note
            assert sum(
                1 for v in finals.values() if v == "suppressed_duplicate_prior_success"
            ) == 1, note
            assert sum(1 for v in finals.values() if v == "owner_closed") == 1, note
            assert any(
                d == "owner_closed_after_injected_skip"
                for d in dict(note.get("fd_dispositions") or ()).values()
            ), note

            # Cleanup-only FD failure (no primary): must surface outward failure.
            only_project, only_fd, only_audit = open_dirs(tmp_path / "cleanup-only")
            only_owned = [only_fd, only_audit]
            only_inv = object()
            note: dict = {"_invocation_id": only_inv}
            raised_cleanup = None
            # R7-LOCAL-1: invalidate BEFORE fallible token() preparation.
            _rs0_one_call_lifetime.last_settlement = {}  # type: ignore[attr-defined]
            try:
                try:
                    only_bearer = token()
                    _body, returned_note = await _rs0_one_call_lifetime(
                        runtime,
                        only_project,
                        bearer_token=only_bearer,
                        mutate=lambda: None,
                        events=events,
                        observed=observed,
                        gate_final=gate_final,
                        release_final=release_final,
                        state=state,
                        fail_at="fd_close",
                        caller_fds=(only_fd, only_audit),
                        invocation_id=only_inv,
                    )
                    note.update(returned_note)
                except AssertionError as error:
                    raised_cleanup = error
                    _recover_invocation_receipt(note)
                    assert "cleanup_only_failures" in str(error), error
                except BaseException as error:
                    _recover_invocation_receipt(note)
                    cleanup_errors.append(error)
                    raise
                assert raised_cleanup is not None, "cleanup-only must fail outward"
                assert isinstance(raised_cleanup, AssertionError), raised_cleanup
                assert "cleanup_only_failures" in str(raised_cleanup), raised_cleanup
                assert note.get("body_error") is None, note
                assert note.get("cleanup_errors"), note
                _require_exact_cleanup(
                    note,
                    expected_substrings=("INJECTED_FD_CLOSE_FAILURE",),
                )
                assert note.get("fd_attempts"), note
                dispositions = dict(note.get("fd_dispositions") or ())
                assert len(dispositions) == 2, note
                assert sum(1 for d in dispositions.values() if d == "closed") == 1, note
                assert (
                    sum(
                        1
                        for d in dispositions.values()
                        if d == "unresolved_injected_failure"
                    )
                    == 1
                ), note
            finally:
                _recover_invocation_receipt(note)
                _owner_finalize_fds(only_owned, note)
            finals = dict(note.get("final_fd_outcomes") or ())
            assert len(finals) == 2, note
            assert sum(
                1 for v in finals.values() if v == "suppressed_duplicate_prior_success"
            ) == 1, note
            assert sum(1 for v in finals.values() if v == "owner_closed") == 1, note

            # Duplicate close after proven successful close (evidence-gated).
            # R6-LOCAL-1: persistent receipt; recover on every raised path before
            # owner finalization (empty initial note is not never-closed proof).
            dup_project, dup_fd, dup_audit = open_dirs(tmp_path / "dup-close")
            dup_owned = [dup_fd, dup_audit]
            dup_inv = object()
            note: dict = {
                "_invocation_id": dup_inv,
                "successfully_closed_fds": (),
                "fd_dispositions": (),
                "final_fd_outcomes": (),
                "cleanup_errors": (),
                "body_error": None,
            }
            # R7-LOCAL-1: invalidate BEFORE fallible token() preparation so a
            # pre-entry failure cannot recover cleanup-only FD settlement and
            # suppress first close of OS-reused FD numbers.
            _rs0_one_call_lifetime.last_settlement = {}  # type: ignore[attr-defined]
            try:
                try:
                    dup_bearer = token()
                    _body, returned_note = await _rs0_one_call_lifetime(
                        runtime,
                        dup_project,
                        bearer_token=dup_bearer,
                        mutate=lambda: None,
                        events=events,
                        observed=observed,
                        gate_final=gate_final,
                        release_final=release_final,
                        state=state,
                        fail_at=None,
                        caller_fds=(dup_fd, dup_audit),
                        force_duplicate_fd_close=True,
                        invocation_id=dup_inv,
                    )
                    note.update(returned_note)
                except BaseException as dup_primary:
                    _recover_invocation_receipt(note)
                    if note.get("body_error") is None:
                        note["body_error"] = dup_primary
                    raise
                assert note.get("successfully_closed_fds"), note
                assert len(note.get("successfully_closed_fds") or ()) == 2, note
                for attempt in note.get("fd_attempts") or ():
                    if attempt[1] == "duplicate_error":
                        assert attempt[0] in note.get("successfully_closed_fds"), note
                _require_exact_cleanup(note, allow_empty=True)
                dup_owned = []  # both successfully closed by helper
            finally:
                _recover_invocation_receipt(note)
                _owner_finalize_fds(dup_owned, note)
            finals = dict(note.get("final_fd_outcomes") or ())
            # When helper closed both, owner finalize sees empty owned list → empty finals
            # or suppressed entries only if somehow still listed.
            if dup_owned:
                assert all(
                    v == "suppressed_duplicate_prior_success" for v in finals.values()
                ), note

        asyncio.run(via_actual_helper())
    except BaseException as error:
        primary_error = error
        raise
    finally:
        read_port_module.observe_file = original_observe  # type: ignore[assignment]
        release_final.set()
        if runtime is not None:
            try:
                asyncio.run(runtime.aclose(timeout=1))
            except BaseException as cleanup_error:
                cleanup_errors.append(cleanup_error)
        successfully_closed: set[int] = set()
        for fd in (project_fd, audit_fd):
            try:
                os.close(fd)
                successfully_closed.add(fd)
            except BaseException as cleanup_error:
                cleanup_errors.append(cleanup_error)
        if primary_error is not None and cleanup_errors:
            try:
                primary_error.add_note(
                    "cleanup_errors="
                    + ",".join(f"{type(err).__name__}:{err!r}" for err in cleanup_errors)
                )
            except Exception:
                pass
        elif primary_error is None and cleanup_errors:
            raise AssertionError(
                "cleanup_only_failures="
                + ",".join(f"{type(err).__name__}:{err!r}" for err in cleanup_errors)
                + f"; successfully_closed_fds={sorted(successfully_closed)}"
            )

