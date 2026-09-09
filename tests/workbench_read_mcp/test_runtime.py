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
from integrations.workbench_read_mcp.app import ProjectReadRefused, ReadCaller
from integrations.workbench_read_mcp.read_port import create_descriptor_read_port
from integrations.workbench_read_mcp.runtime import (
    RuntimeCloseIncomplete,
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
                assert body["structuredContent"]["content"] == "runtime source\n"
                assert len(body["structuredContent"]) == 22

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
    asyncio.run(runtime.aclose(timeout=1))
    os.close(project_fd)
    os.close(audit_fd)
