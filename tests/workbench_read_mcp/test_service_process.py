"""Process-boundary tests for the concrete Workbench Read service launcher."""
from __future__ import annotations

import base64
import contextlib
import hashlib
import os
import signal
import socket
import time
import importlib
import io
import json
from pathlib import Path
import subprocess
import sys

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/mastermind_workbench_read_server.py"


CHILD_JWKS_FETCHER_SOURCE = (
    'import asyncio\n'
    'import base64\n'
    'import os\n'
    'import runpy\n'
    'import sys\n'
    'import threading\n'
    'from pathlib import Path\n'
    'from integrations.business_mcp_auth.jwks import JWKS_TIMEOUT_SECONDS, MAX_JWKS_BYTES\n'
    'from integrations.workbench_read_mcp import service\n'
    'config_path, encoded_jwks, launcher_path, shutdown_case = sys.argv[1:]\n'
    "payload = base64.b64decode(encoded_jwks.encode('ascii'), validate=True)\n"
    'fixture_root = Path(config_path).parent\n'
    'class StaticFetcher:\n'
    '    def __init__(self, policy): self.policy = policy\n'
    '    async def fetch(self, *, url, timeout_seconds, max_bytes):\n'
    '        if (url != self.policy.jwks_uri or timeout_seconds != JWKS_TIMEOUT_SECONDS\n'
    '                or max_bytes != MAX_JWKS_BYTES):\n'
    "            raise RuntimeError('fixture fetch contract mismatch')\n"
    '        return payload\n'
    'service.HttpxJwksFetcher = StaticFetcher\n'
    "if shutdown_case == 'incomplete':\n"
    '    close_attempt_finished = threading.Event()\n'
    '    real_close_runtime = service._close_runtime\n'
    '    async def close_runtime_with_completion(runtime, config, state):\n'
    '        try:\n'
    '            await real_close_runtime(runtime, config, state)\n'
    '        finally:\n'
    '            close_attempt_finished.set()\n'
    '    service._close_runtime = close_runtime_with_completion\n'
    '    real_create_runtime = service.create_runtime\n'
    '    async def create_runtime_with_physical_work(config):\n'
    '        runtime = await real_create_runtime(config)\n'
    '        def physical_read():\n'
    "            fd = os.open('source.txt', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=runtime.root_fd)\n"
    '            try:\n'
    "                assert os.read(fd, 1024) == b'p0 subprocess sentinel\\n'\n"
    "                (fixture_root / 'physical-started').write_text('started')\n"
    '                # Retain actual descriptor work until the real close attempt ends.\n'
    '                # A bounded backstop fails the fixture if shutdown never arrives.\n'
    "                assert close_attempt_finished.wait(5), 'close attempt did not finish'\n"
    '            finally:\n'
    '                os.close(fd)\n'
    "                (fixture_root / 'physical-finished').write_text('finished')\n"
    '        async def await_trigger():\n'
    "            while not (fixture_root / 'start-physical').exists():\n"
    '                await asyncio.sleep(0.01)\n'
    '            await runtime.run_io(physical_read)\n'
    '        task = asyncio.create_task(await_trigger())\n'
    '        task.add_done_callback(lambda done: None if done.cancelled() else done.exception())\n'
    '        return runtime\n'
    '    service.create_runtime = create_runtime_with_physical_work\n'
    "sys.argv = [launcher_path, '--config', config_path]\n"
    "runpy.run_path(launcher_path, run_name='__main__')\n"
)


def test_child_jwks_fixture_source_compiles() -> None:
    compile(CHILD_JWKS_FETCHER_SOURCE, "<workbench-process-jwks-fixture>", "exec")


def test_describe_remains_dependency_free_and_truthful() -> None:
    completed = subprocess.run(
        [sys.executable, "-S", str(SCRIPT), "--describe"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "capability": "BUILT_NOT_PROVEN",
        "mode": "configured-loopback-service",
        "tool": "read_project_file",
        "config_schema": "mastermind.workbench_read_service.v1",
        "installed": False,
    }
    assert completed.stderr == ""


def test_legacy_parallel_authority_flags_are_rejected() -> None:
    launcher = importlib.import_module("scripts.mastermind_workbench_read_server")
    for args in (
        ["--host", "127.0.0.1"],
        ["--port", "8765"],
        ["--root", "/"],
        ["--factory", "evil:main"],
    ):
        with contextlib.redirect_stderr(io.StringIO()):
            with pytest.raises(SystemExit) as captured:
                launcher.main(args)
        assert captured.value.code == 2


def test_config_is_required_and_prebind_refusal_is_exit_2(tmp_path: Path) -> None:
    launcher = importlib.import_module("scripts.mastermind_workbench_read_server")
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        assert launcher.main([]) == 2
    assert err.getvalue().strip() == "SERVICE_CONFIGURATION_REQUIRED"

    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        assert launcher.main(["--config", str(tmp_path / "missing.json")]) == 2
    assert err.getvalue().strip() == "SERVICE_CONFIGURATION_REFUSED"


def test_launcher_delegates_exact_config_path_and_preserves_service_exit(monkeypatch, tmp_path: Path) -> None:
    launcher = importlib.import_module("scripts.mastermind_workbench_read_server")
    path = tmp_path / "service.json"
    path.write_text("{}", encoding="ascii")
    calls = []

    def fake(path_value: str) -> int:
        calls.append(path_value)
        return 4

    monkeypatch.setattr(launcher, "_run_configured_service", fake)
    assert launcher.main(["--config", str(path)]) == 4
    assert calls == [str(path)]



@pytest.mark.parametrize(
    ("shutdown_case", "expected_exit"),
    [("clean", 0), ("incomplete", 3), ("audit-drift", 4)],
)
def test_real_subprocess_launcher_signed_initialize_list_call_and_shutdown(
    tmp_path: Path, shutdown_case: str, expected_exit: int
) -> None:
    if os.name == "nt":
        pytest.skip("P0 service target and graceful signal proof are POSIX/Darwin")

    repo_root = Path(__file__).resolve().parents[2]
    project = tmp_path / "project"
    audit = tmp_path / "audit"
    project.mkdir(mode=0o700)
    audit.mkdir(mode=0o700)
    source = project / "source.txt"
    sentinel = "p0 subprocess sentinel\n"
    source.write_text(sentinel, encoding="utf-8")
    source.chmod(0o600)

    issuer = "https://identity.read0.example"
    resource = "https://read0.example/mcp"
    subject = "process-reader"
    client_id = "read0-process-client"
    now = int(time.time())
    subject_digest = hashlib.sha256(f"{issuer}\n{subject}".encode()).hexdigest()
    client_ref = hashlib.sha256(f"{issuer}\nclient\n{client_id}".encode()).hexdigest()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public = {name: public[name] for name in ("kty", "n", "e")}
    public.update(kid="p0-process", use="sig", alg="RS256")
    jwks_payload = json.dumps({"keys": [public]}, separators=(",", ":")).encode("ascii")

    policy = {
        "schema": "mastermind.business_mcp_auth_policy.v1",
        "policy_id": "read0.process.fixture",
        "resource": resource,
        "resource_metadata_url": "https://read0.example/.well-known/oauth-protected-resource/mcp",
        "issuer": issuer,
        "authorization_servers": [issuer],
        "jwks_uri": issuer + "/jwks",
        "required_scopes": ["workbench.read"],
        "allowed_subject_digests": [subject_digest],
        "allowed_algorithms": ["RS256"],
        "clock_skew_seconds": 0,
        "max_token_lifetime_seconds": 3600,
        "jwks_cache_ttl_seconds": 60,
        "unknown_kid_refresh_cooldown_seconds": 1,
        "fetch_failure_backoff_seconds": 1,
    }
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy, separators=(",", ":")), encoding="ascii")
    policy_path.chmod(0o600)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        candidate.bind(("127.0.0.1", 0))
        port = candidate.getsockname()[1]
    stable = lambda prefix, label: prefix + hashlib.sha256(label.encode()).hexdigest()
    config = {
        "schema": "mastermind.workbench_read_service.v1",
        "policy_file": str(policy_path),
        "project_root": str(project),
        "audit_directory": str(audit),
        "bind_host": "127.0.0.1",
        "bind_port": port,
        "incoming_authority": f"127.0.0.1:{port}",
        "max_concurrency": 2,
        "io_timeout_seconds": 5.0,
        "close_timeout_seconds": 0.1 if shutdown_case == "incomplete" else 5.0,
        "lease": {
            "expected_subject_digest": subject_digest,
            "expected_client_ref": client_ref,
            "resource": resource,
            "required_scopes": ["workbench.read"],
            "project_ref": stable("project:", "process-project"),
            "context_ref": stable("context:", "process-context"),
            "owner_ref": stable("owner:", "process-owner"),
            "generation": stable("generation:", "process-generation"),
            "allowed_paths": ["source.txt"],
            "committed_head": "1" * 40,
            "lease_expires_at_ms": (now + 600) * 1000,
        },
    }
    config_path = tmp_path / "service.json"
    config_path.write_text(json.dumps(config, separators=(",", ":")), encoding="ascii")
    config_path.chmod(0o600)

    # The production fetcher remains untouched.  A child-process-only patch keeps
    # the real cache/JWT/policy path while avoiding privileged port 443 or a
    # provider/tunnel merely to host a source-test JWKS fixture.
    child = tmp_path / "run_service_fixture.py"
    child.write_text(CHILD_JWKS_FETCHER_SOURCE, encoding="ascii")
    encoded_jwks = base64.b64encode(jwks_payload).decode("ascii")
    process = subprocess.Popen(
        [sys.executable, "-B", str(child), str(config_path), encoded_jwks, str(SCRIPT), shutdown_case],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=1.0)
    failure: BaseException | None = None
    last_ready_status: int | None = None
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                pytest.fail(f"service exited before ready: {process.returncode}\n{stdout}\n{stderr}")
            try:
                last_ready_status = client.get("/readyz").status_code
                if last_ready_status == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.05)
        else:
            pytest.fail("service did not become ready")

        token = jwt.encode(
            {
                "iss": issuer,
                "sub": subject,
                "aud": resource,
                "iat": now - 1,
                "exp": now + 300,
                "scope": "workbench.read",
                "client_id": client_id,
            },
            private_key,
            algorithm="RS256",
            headers={"kid": "p0-process"},
        )
        base_headers = {
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-03-26",
            "Authorization": "Bearer " + token,
        }
        initialize = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "read0-process-fixture", "version": "1"},
            },
        }
        refused = client.post(
            "/mcp", headers={**base_headers, "Host": "wrong.example:443"}, json=initialize
        )
        assert refused.status_code != 200

        headers = {**base_headers, "Host": f"127.0.0.1:{port}"}
        hello = client.post("/mcp", headers=headers, json=initialize)
        assert hello.status_code == 200, hello.text
        assert "serverInfo" in hello.json()["result"]

        listed = client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert listed.status_code == 200, listed.text
        tools = listed.json()["result"]["tools"]
        assert [tool["name"] for tool in tools] == ["read_project_file"]
        assert tools[0]["annotations"]["readOnlyHint"] is True

        expected_hash = hashlib.sha256(sentinel.encode()).hexdigest()
        called = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "read_project_file",
                    "arguments": {
                        "project_ref": config["lease"]["project_ref"],
                        "relative_path": "source.txt",
                        "expected_sha256": expected_hash,
                    },
                },
            },
        )
        assert called.status_code == 200, called.text
        result = called.json()["result"]
        assert result["isError"] is False
        observed = result["structuredContent"]
        assert observed["content"] == sentinel
        assert observed["file_sha256"] == expected_hash
        assert observed["project_ref"] == config["lease"]["project_ref"]
        assert str(project) not in called.text

        audit_path = audit / "auth-audit.jsonl"
        assert audit_path.is_file()
        audit_text = audit_path.read_text(encoding="ascii")
        audit_events = [json.loads(line) for line in audit_text.splitlines() if line]
        assert audit_events
        assert any(event["accepted"] is True for event in audit_events)
        assert all(
            set(event) == {"schema", "policy_id", "code", "accepted"}
            for event in audit_events
        )
        for private_value in (token, sentinel, str(project), subject, client_id):
            assert private_value not in audit_text

        if shutdown_case == "incomplete":
            (tmp_path / "start-physical").write_text("start", encoding="ascii")
            deadline = time.monotonic() + 5
            while not (tmp_path / "physical-started").exists():
                assert process.poll() is None, "process exited before physical read started"
                assert time.monotonic() < deadline, "physical read did not start"
                time.sleep(0.01)
        elif shutdown_case == "audit-drift":
            audit_path.chmod(0o640)
        shutdown_started = time.monotonic()
    except BaseException as error:
        failure = error
        raise
    finally:
        client.close()
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)
            pytest.fail(f"service failed to drain after SIGTERM\n{stdout}\n{stderr}")
        if failure is not None:
            failure.add_note(
                f"last_ready_status={last_ready_status}; exit={process.returncode}\n"
                f"stdout={stdout}\nstderr={stderr}"
            )
    assert process.returncode == expected_exit, f"stdout={stdout}\nstderr={stderr}"
    assert time.monotonic() - shutdown_started < 10
    assert token not in stdout + stderr
    if shutdown_case == "incomplete":
        assert (tmp_path / "physical-finished").read_text() == "finished"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as disconnected:
        disconnected.settimeout(1)
        assert disconnected.connect_ex(("127.0.0.1", port)) != 0


def test_direct_launcher_imports_owned_source_without_pythonpath(tmp_path: Path) -> None:
    environment = {name: value for name, value in os.environ.items()
                   if name not in {"PYTHONPATH", "PYTHONHOME"}}
    completed = subprocess.run(
        [sys.executable, "-I", "-B", str(SCRIPT), "--config", str(tmp_path / "absent.json")],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=10,
    )
    assert completed.returncode == 2, completed.stderr
    assert completed.stderr.strip() == "SERVICE_CONFIGURATION_REFUSED"
    assert completed.stdout == ""
