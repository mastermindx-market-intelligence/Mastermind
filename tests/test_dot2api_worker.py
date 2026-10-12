from __future__ import annotations

import asyncio
import dataclasses
import io
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from control_plane.codex_worker import ResultValidationError
from control_plane.dot2api_worker import Dot2ApiWorkerAdapter, _read_json
from control_plane.worker_adapter import adapter_descriptor, adapter_implementation
from control_plane.worker_execution_contract import (
    WorkerLaunchSpec,
    WorkerRecoveryBinding,
    WorkerRunStatus,
)
from integrations.dot2api.client import (
    Dot2ApiClient,
    Dot2ApiEffectUnknown,
    Dot2ApiProtocolError,
)


_SECRET = "dot2api-test-secret-do-not-persist"
_TASK_ID = "task_fixture"


class _State:
    def __init__(self, mode: str = "complete") -> None:
        self.mode = mode
        self.submissions = 0
        self.gets = 0
        self.cancels = 0
        self.last_submit: dict | None = None

    def task(self, status: str) -> dict:
        result = None
        error = None
        attempts = 0
        if status == "completed":
            attempts = 1
            result = {
                "content": json.dumps(
                    {"decision": "PASS", "artifacts": []},
                    sort_keys=True,
                )
            }
        elif status == "cancelled":
            error = "fixture cancellation"
        return {
            "id": _TASK_ID,
            "sequence": 1,
            "queue": "dot",
            "instructions": "fixture",
            "payload": {"messages": []},
            "status": status,
            "result": result,
            "error": error,
            "attempts": attempts,
            "max_attempts": 1,
            "revision": 2 if status != "queued" else 1,
            "created_at": "2026-10-11T20:00:00Z",
            "updated_at": "2026-10-11T20:00:01Z",
            "expires_at": "2026-10-11T20:10:00Z",
            "available_at": "2026-10-11T20:00:00Z",
            "lease_expires_at": None,
        }


def _handler(state: _State):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A003
            return

        def _json(self, status: int, value: dict) -> None:
            raw = json.dumps(value, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _authorized(self) -> bool:
            if self.headers.get("Authorization") == "Bearer " + _SECRET:
                return True
            self._json(
                401,
                {"error": {"code": "unauthorized", "message": "Authentication required"}},
            )
            return False

        def do_POST(self):  # noqa: N802
            if not self._authorized():
                return
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            if self.path == "/v1/tasks":
                state.submissions += 1
                state.last_submit = body
                if state.mode == "drop-submit":
                    try:
                        self.connection.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    self.connection.close()
                    return
                self._json(200, {"task": state.task("queued")})
                return
            if self.path == "/v1/tools/cancel_task":
                state.cancels += 1
                if state.mode == "complete-before-cancel":
                    self._json(
                        409,
                        {"error": {"code": "conflict", "message": "Task is terminal"}},
                    )
                    return
                state.mode = "cancelled"
                self._json(200, {"task": state.task("cancelled")})
                return
            self._json(404, {"error": {"code": "not_found", "message": "not found"}})

        def do_GET(self):  # noqa: N802
            if self.path == "/readyz":
                self._json(200, {"status": "ready"})
                return
            if not self._authorized():
                return
            if self.path == "/v1/tasks/" + _TASK_ID:
                state.gets += 1
                if state.mode == "read-unavailable" or (
                    state.mode == "read-flaky" and state.gets == 1
                ):
                    self._json(
                        503,
                        {"error": {"code": "backend_unavailable", "message": "later"}},
                    )
                    return
                if state.mode in {"complete", "complete-before-cancel", "read-flaky"}:
                    status = "completed"
                elif state.mode == "cancelled":
                    status = "cancelled"
                else:
                    status = "queued"
                self._json(200, {"task": state.task(status)})
                return
            self._json(404, {"error": {"code": "not_found", "message": "not found"}})

    return Handler


class _Server:
    def __init__(self, mode: str = "complete") -> None:
        self.state = _State(mode)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _handler(self.state))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_port}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.thread.join(timeout=5)
        self.httpd.server_close()


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
        },
    )
    return completed.stdout.strip()


def _spec(tmp_path: Path, *, authorities: tuple[str, ...] = ("READ",)):
    tmp_path.mkdir(mode=0o700, parents=True, exist_ok=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700)
    _git(workspace, "init", "-q")
    _git(workspace, "config", "user.email", "fixture@example.invalid")
    _git(workspace, "config", "user.name", "Fixture")
    (workspace / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(workspace, "add", "README.md")
    _git(workspace, "commit", "-qm", "fixture")
    head = _git(workspace, "rev-parse", "HEAD")

    run_dir = tmp_path / "run"
    run_dir.mkdir(mode=0o700)
    input_dir = run_dir / "input"
    input_dir.mkdir(mode=0o700)
    schema = input_dir / "result.schema.json"
    schema.write_text(
        json.dumps(
            {
                "type": "object",
                "required": ["decision", "artifacts"],
                "properties": {
                    "decision": {"const": "PASS"},
                    "artifacts": {"type": "array", "maxItems": 0},
                },
                "additionalProperties": False,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return WorkerLaunchSpec(
        run_id="run-1",
        job_id="job-1",
        worker_id="worker-1",
        workspace_path=workspace,
        run_dir=run_dir,
        prompt="Assess the fixture and return the requested structured result.",
        result_schema_path=schema,
        authorities=authorities,
        model="dot",
        timeout_seconds=10,
        expected_base_sha=head,
    )


def test_reviewed_dot2api_adapter_is_registered_but_not_live_qualified():
    descriptor = adapter_descriptor("dot2api")
    assert descriptor.implemented is False
    assert adapter_implementation("dot2api") is Dot2ApiWorkerAdapter


def test_dot2api_client_does_not_retry_ambiguous_submit():
    with _Server("drop-submit") as server:
        client = Dot2ApiClient(
            server.base_url,
            token_loader=lambda: _SECRET,
            timeout_seconds=2,
        )
        with pytest.raises(Dot2ApiEffectUnknown):
            client.submit_chat_task(
                queue="dot",
                idempotency_key="request-1",
                messages=[{"role": "user", "content": "hello"}],
                ttl_seconds=60,
                max_attempts=1,
            )
        assert server.state.submissions == 1


def test_dot2api_worker_round_trip_persists_task_identity_and_validates_schema(
    tmp_path: Path,
):
    async def scenario():
        spec = _spec(tmp_path)
        with _Server("complete") as server:
            adapter = Dot2ApiWorkerAdapter(
                server.base_url,
                credential_loader=lambda: _SECRET,
                poll_seconds=0.2,
                submission_timeout_seconds=5,
            )
            ref = await adapter.start(spec)
            assert ref.provider_session_id == _TASK_ID
            assert adapter.launch_attestation(ref).isolation_manifest_sha256 is None

            receipt = await adapter.collect_result(ref)
            assert receipt.result.status is WorkerRunStatus.SUCCEEDED
            assert dict(receipt.result.structured_output or {}) == {
                "decision": "PASS",
                "artifacts": (),
            }
            assert receipt.result.provider_session_id == _TASK_ID
            assert receipt.process_ref.provider_session_id == _TASK_ID
            assert server.state.submissions == 1
            assert server.state.last_submit is not None
            assert server.state.last_submit["max_attempts"] == 1
            assert server.state.last_submit["idempotency_key"].startswith("mmx-")
            assert [m["role"] for m in server.state.last_submit["payload"]["messages"]] == [
                "system",
                "user",
            ]

            attestation = json.dumps(
                adapter.launch_attestation(ref).to_dict(), sort_keys=True
            )
            assert _SECRET not in attestation
            for path in spec.run_dir.rglob("*"):
                if path.is_file():
                    assert _SECRET.encode("utf-8") not in path.read_bytes()

    asyncio.run(scenario())


def test_dot2api_worker_cancel_maps_to_exact_provider_task(tmp_path: Path):
    async def scenario():
        spec = _spec(tmp_path)
        with _Server("hold") as server:
            adapter = Dot2ApiWorkerAdapter(
                server.base_url,
                credential_loader=lambda: _SECRET,
                poll_seconds=0.2,
                submission_timeout_seconds=5,
            )
            ref = await adapter.start(spec)
            cancellation = await adapter.cancel(ref, "fixture stop")
            assert cancellation.run_id == spec.run_id
            assert server.state.cancels == 1
            receipt = await adapter.collect_result(ref)
            assert receipt.result.status is WorkerRunStatus.CANCELLED
            assert receipt.result.provider_session_id == _TASK_ID

    asyncio.run(scenario())


def test_dot2api_worker_refuses_write_authority(tmp_path: Path):
    async def scenario():
        spec = _spec(tmp_path, authorities=("READ", "WRITE_BRANCH"))
        with _Server("complete") as server:
            adapter = Dot2ApiWorkerAdapter(
                server.base_url,
                credential_loader=lambda: _SECRET,
            )
            with pytest.raises(Exception, match="READ/RESEARCH-only"):
                await adapter.start(spec)
            assert server.state.submissions == 0

    asyncio.run(scenario())


class _StaticResponse:
    def __init__(self, raw: bytes, status: int = 200) -> None:
        self.raw = raw
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, maximum: int = -1) -> bytes:
        return self.raw if maximum < 0 else self.raw[:maximum]


class _StaticOpener:
    def __init__(self, response=None, error=None) -> None:
        self.response = response
        self.error = error
        self.calls = 0

    def open(self, request, timeout):  # noqa: ANN001
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.response


def _task_wire(*, task_id=_TASK_ID, queue="dot", max_attempts=1, result=None) -> dict:
    return {
        "task": {
            "id": task_id,
            "sequence": 1,
            "queue": queue,
            "instructions": "fixture",
            "payload": {"messages": []},
            "status": "queued",
            "result": result,
            "error": None,
            "attempts": 0,
            "max_attempts": max_attempts,
            "revision": 1,
            "created_at": "2026-10-11T20:00:00Z",
            "updated_at": "2026-10-11T20:00:01Z",
            "expires_at": "2026-10-11T20:10:00Z",
            "available_at": "2026-10-11T20:00:00Z",
            "lease_expires_at": None,
        }
    }


def test_dot2api_client_rejects_duplicate_and_nonfinite_json():
    duplicate = (
        b'{"task":{"id":"task_fixture","id":"task_other","sequence":1,'
        b'"queue":"dot","instructions":"fixture","payload":{},"status":"queued",'
        b'"result":null,"error":null,"attempts":0,"max_attempts":1,"revision":1,'
        b'"created_at":"a","updated_at":"b","expires_at":"c",'
        b'"available_at":"d","lease_expires_at":null}}'
    )
    for raw in (duplicate, json.dumps(_task_wire()).replace('null', 'NaN', 1).encode()):
        client = Dot2ApiClient(
            "http://127.0.0.1:8788",
            token_loader=lambda: _SECRET,
            opener=_StaticOpener(_StaticResponse(raw)),
        )
        with pytest.raises(Dot2ApiProtocolError):
            client.get_task(_TASK_ID)


def test_dot2api_client_treats_mutating_server_failure_as_effect_unknown():
    error = urllib.error.HTTPError(
        "http://127.0.0.1:8788/v1/tasks",
        503,
        "unavailable",
        {},
        io.BytesIO(b'{"error":{"code":"backend_unavailable","message":"later"}}'),
    )
    opener = _StaticOpener(error=error)
    client = Dot2ApiClient(
        "http://127.0.0.1:8788",
        token_loader=lambda: _SECRET,
        opener=opener,
    )
    with pytest.raises(Dot2ApiEffectUnknown):
        client.submit_chat_task(
            queue="dot",
            idempotency_key="request-503",
            messages=[{"role": "user", "content": "hello"}],
            ttl_seconds=60,
            max_attempts=1,
        )
    assert opener.calls == 1


@pytest.mark.parametrize(
    ("queue", "max_attempts"),
    [("other", 1), ("dot", 2)],
)
def test_dot2api_submit_binds_queue_and_single_attempt(queue, max_attempts):
    raw = json.dumps(_task_wire(queue=queue, max_attempts=max_attempts)).encode()
    client = Dot2ApiClient(
        "http://127.0.0.1:8788",
        token_loader=lambda: _SECRET,
        opener=_StaticOpener(_StaticResponse(raw)),
    )
    with pytest.raises(Dot2ApiProtocolError):
        client.submit_chat_task(
            queue="dot",
            idempotency_key="request-binding",
            messages=[{"role": "user", "content": "hello"}],
            ttl_seconds=60,
            max_attempts=1,
        )


@pytest.mark.parametrize(
    "wire",
    [
        _task_wire(task_id="task_foreign"),
        _task_wire(queue="other"),
        _task_wire(max_attempts=2),
    ],
)
def test_dot2api_get_rebinds_exact_task_queue_and_attempt_ceiling(wire):
    client = Dot2ApiClient(
        "http://127.0.0.1:8788",
        token_loader=lambda: _SECRET,
        opener=_StaticOpener(_StaticResponse(json.dumps(wire).encode())),
    )
    with pytest.raises(Dot2ApiProtocolError):
        client.get_task(
            _TASK_ID, expected_queue="dot", expected_max_attempts=1
        )


def test_dot2api_cancel_rebinds_exact_returned_task_identity():
    client = Dot2ApiClient(
        "http://127.0.0.1:8788",
        token_loader=lambda: _SECRET,
        opener=_StaticOpener(
            _StaticResponse(json.dumps(_task_wire(task_id="task_foreign")).encode())
        ),
    )
    with pytest.raises(Dot2ApiProtocolError):
        client.cancel_task(
            _TASK_ID,
            reason="stop",
            expected_queue="dot",
            expected_max_attempts=1,
        )


def test_dot2api_worker_retries_transient_status_read_without_resubmission(
    tmp_path: Path,
):
    async def scenario():
        spec = _spec(tmp_path)
        with _Server("read-flaky") as server:
            adapter = Dot2ApiWorkerAdapter(
                server.base_url,
                credential_loader=lambda: _SECRET,
                poll_seconds=0.2,
                submission_timeout_seconds=5,
            )
            ref = await adapter.start(spec)
            receipt = await adapter.collect_result(ref)
            assert receipt.result.status is WorkerRunStatus.SUCCEEDED
            assert server.state.submissions == 1
            assert server.state.gets >= 2

    asyncio.run(scenario())


def test_dot2api_worker_accepts_read_research_authority(tmp_path: Path):
    async def scenario():
        spec = _spec(tmp_path, authorities=("READ", "RESEARCH"))
        with _Server("complete") as server:
            adapter = Dot2ApiWorkerAdapter(
                server.base_url,
                credential_loader=lambda: _SECRET,
                poll_seconds=0.2,
                submission_timeout_seconds=5,
            )
            ref = await adapter.start(spec)
            receipt = await adapter.collect_result(ref)
            assert receipt.result.status is WorkerRunStatus.SUCCEEDED
            assert server.state.submissions == 1

    asyncio.run(scenario())


def test_dot2api_worker_requires_loopback_provider_origin():
    with pytest.raises(ValueError, match="loopback"):
        Dot2ApiWorkerAdapter(
            "https://dot2api.example.com",
            credential_loader=lambda: _SECRET,
        )


def test_dot2api_worker_requires_secret_canary_when_requested(tmp_path: Path):
    async def scenario():
        spec = dataclasses.replace(
            _spec(tmp_path),
            require_secret_canary=True,
            secret_canary_verdict={},
        )
        with _Server("complete") as server:
            adapter = Dot2ApiWorkerAdapter(
                server.base_url,
                credential_loader=lambda: _SECRET,
            )
            with pytest.raises(Exception, match="secret canary"):
                await adapter.start(spec)
            assert server.state.submissions == 0

    asyncio.run(scenario())


def test_dot2api_cancel_losing_to_completion_preserves_completed_result(tmp_path: Path):
    async def scenario():
        spec = _spec(tmp_path)
        with _Server("complete-before-cancel") as server:
            adapter = Dot2ApiWorkerAdapter(
                server.base_url,
                credential_loader=lambda: _SECRET,
                poll_seconds=0.2,
                submission_timeout_seconds=5,
            )
            ref = await adapter.start(spec)
            await adapter.cancel(ref, "late stop")
            receipt = await adapter.collect_result(ref)
            assert receipt.result.status is WorkerRunStatus.SUCCEEDED
            assert receipt.result.error is None
            assert server.state.cancels == 1

    asyncio.run(scenario())


def test_dot2api_worker_refuses_transport_script_drift_before_submit(tmp_path: Path):
    async def scenario():
        spec = _spec(tmp_path / "spec")
        source = Path(__file__).resolve().parents[1] / "ops" / "executive_os" / "dot2api_transport_worker.py"
        script = tmp_path / "dot2api_transport_worker.py"
        shutil.copy2(source, script)
        script.chmod(0o700)
        with _Server("complete") as server:
            adapter = Dot2ApiWorkerAdapter(
                server.base_url,
                credential_loader=lambda: _SECRET,
                transport_script=script,
            )
            script.write_text(script.read_text() + "\n# drift\n", encoding="utf-8")
            with pytest.raises(Exception, match="changed|drift|immutable"):
                await adapter.start(spec)
            assert server.state.submissions == 0

    asyncio.run(scenario())


def test_dot2api_recovery_reads_exact_task_without_resubmission(tmp_path: Path):
    async def scenario():
        spec = _spec(tmp_path)
        with _Server("hold") as server:
            first = Dot2ApiWorkerAdapter(
                server.base_url,
                credential_loader=lambda: _SECRET,
                poll_seconds=0.2,
                submission_timeout_seconds=5,
            )
            ref = await first.start(spec)
            prompt_path = spec.run_dir / "input" / "worker-prompt.txt"
            prompt_path.write_text(spec.prompt, encoding="utf-8")
            prompt_path.chmod(0o600)
            binding = WorkerRecoveryBinding.bind(
                adapter_id="dot2api",
                spec=spec,
                process_ref=ref,
                prompt_path=prompt_path,
            )
            os.killpg(ref.pgid, signal.SIGTERM)
            await first._runs[spec.run_id].process.wait()
            server.state.mode = "complete"

            recovered = Dot2ApiWorkerAdapter(
                server.base_url,
                credential_loader=lambda: _SECRET,
                poll_seconds=0.2,
            )
            recovered_ref = recovered.reattach(spec, binding)
            receipt = await recovered.collect_result(recovered_ref)
            assert receipt.result.status is WorkerRunStatus.SUCCEEDED
            assert receipt.result.provider_session_id == _TASK_ID
            assert server.state.submissions == 1

    asyncio.run(scenario())



def test_dot2api_transport_worker_bounds_unavailable_status_reads(tmp_path: Path):
    script = Path(__file__).resolve().parents[1] / "ops" / "executive_os" / "dot2api_transport_worker.py"
    input_path = tmp_path / "input.json"
    provider_path = tmp_path / "provider.json"
    result_path = tmp_path / "result.json"
    with _Server("read-unavailable") as server:
        input_path.write_text(
            json.dumps(
                {
                    "base_url": server.base_url,
                    "queue": "dot",
                    "idempotency_key": "deadline-test",
                    "messages": [{"role": "user", "content": "hello"}],
                    "ttl_seconds": 60,
                    "max_attempts": 1,
                    "poll_seconds": 0.1,
                    "poll_deadline_seconds": 0.5,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        completed = subprocess.run(
            [
                sys.executable,
                str(script),
                "--input",
                str(input_path),
                "--provider",
                str(provider_path),
                "--result",
                str(result_path),
            ],
            env={**os.environ, "MMX_DOT2API_TOKEN": _SECRET},
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    assert completed.returncode == 74
    binding = json.loads(provider_path.read_text(encoding="utf-8"))
    assert binding["task_id"] == _TASK_ID
    assert server.state.submissions == 1
    assert server.state.gets >= 1
    assert not result_path.exists()
    assert "dot2api_poll_deadline" in completed.stderr



def test_dot2api_durable_json_rejects_duplicate_and_nonfinite_values(tmp_path: Path):
    for index, raw in enumerate(
        (
            b'{"task_id":"task_fixture","task_id":"task_other"}\n',
            b'{"task_id":"task_fixture","revision":NaN}\n',
            b'{"task_id":"task_fixture","revision":1e999}\n',
        )
    ):
        path = tmp_path / f"durable-{index}.json"
        path.write_bytes(raw)
        with pytest.raises(ResultValidationError, match="durable JSON"):
            _read_json(path, 4096)
