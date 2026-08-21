"""control_plane.executive_ceo_ingress — MAS-75 PR-A dedicated CeoIngress surface.

Hermetic: real AF_UNIX sockets + a real Runtime on ``tmp_path`` SQLite,
following the existing patterns in ``tests/test_executive_service.py``.  This
file proves the full §17 adversarial matrix plus the R1 security correction
(§2.2 startup latch, §3.3 no-path/no-secret, §5 mutation-detection) and the R2
lifecycle correction (§4 marker/lock invariants), for the NEW dedicated
CeoIngress listener composed onto ``ExecutiveControlService``.  It does not
modify any existing test in ``tests/test_executive_service.py``.

Law-item -> test-name mapping is recorded in the module docstring of the
worker's final report, not duplicated here; test names below are written to be
self-describing against the §17 family headings.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

from common.redaction import sanitize_external_text
from control_plane import ceo_intent
from control_plane import executive_ceo_ingress as ceo_ingress
from control_plane.executive_authority import AuthorityDenied
from control_plane.executive_runtime import Runtime
from control_plane.executive_service import ExecutiveControlService, ServiceConfig


# ---------------------------------------------------------------------------
# fixtures / fixtures-adjacent helpers (mirrors tests/test_executive_service.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def short_socket_root():
    # Darwin's sockaddr_un path ceiling is only 104 bytes.
    value = Path(tempfile.mkdtemp(prefix="mmx-ci-", dir="/tmp"))
    try:
        yield value
    finally:
        shutil.rmtree(value, ignore_errors=True)


def _source_repository(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "proof-source"
    if not (source / ".git").is_dir():
        source.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(source)], check=True)
        subprocess.run(
            ["git", "-C", str(source), "config", "user.name", "Executive Fixture"],
            check=True,
        )
        subprocess.run(
            [
                "git", "-C", str(source), "config", "user.email",
                "executive-fixture@example.invalid",
            ],
            check=True,
        )
        (source / "README.md").write_text("# Exact proof base\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(source), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(source), "commit", "-q", "-m", "proof base"], check=True
        )
    base_sha = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True, stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    return source, base_sha


def _config(tmp_path: Path, *, socket_root: Path, **overrides: Any) -> ServiceConfig:
    source, base_sha = _source_repository(tmp_path)
    values = {
        "runtime_root": tmp_path / "runtime",
        "socket_path": socket_root / "operator.sock",
        "proof_source_repository": source,
        "proof_workspace_root": tmp_path / "workspaces",
        "proof_base_sha": base_sha,
        "allowed_peer_uids": (os.geteuid(),),
        "shutdown_grace_seconds": 0.2,
    }
    values.update(overrides)
    return ServiceConfig(**values)


class _FakeSupervisor:
    """CeoIngress never dispatches, so this fixture only needs restart
    reconciliation — no ``start_job``/``finish_job`` is ever exercised here."""

    def reconcile_restart(self, *, requeue_lost: bool = False) -> list[Any]:
        return []


class _FakeGrounding:
    """Injected grounding provider (§10).  ``sequence`` is consumed one call at
    a time (last value repeats) so a test can model grounding movement between
    the first and second ``observe()`` call."""

    def __init__(
        self, sequence: list[dict[str, str]] | None = None, *, error: Exception | None = None
    ) -> None:
        self._sequence = list(sequence) if sequence is not None else [dict(GROUNDING_A)]
        self._error = error
        self.calls = 0

    def observe(self) -> dict[str, str]:
        self.calls += 1
        if self._error is not None:
            raise self._error
        if len(self._sequence) > 1:
            return dict(self._sequence.pop(0))
        return dict(self._sequence[0])


GROUNDING_A = {
    "mastermind_sha": "1111111111111111111111111111111111111111",
    "macro_sha": "2222222222222222222222222222222222222222",
    "boot_packet_schema": ceo_ingress.BOOT_PACKET_SCHEMA,
}
GROUNDING_B = {
    "mastermind_sha": "3333333333333333333333333333333333333333",
    "macro_sha": "4444444444444444444444444444444444444444",
    "boot_packet_schema": ceo_ingress.BOOT_PACKET_SCHEMA,
}

#: §6.2/§15.1 frozen literal cross-transport vector — a regression pin, never
#: a value computed by the function under test.
LITERAL_OPERATION_KEY = "options-chain-browser-closure-001"
LITERAL_SLACK_INTENT_ID = "slack-4e40f3d7656227ee9dcead6b00c9d5f2"


def _research_request(**overrides: Any) -> dict[str, Any]:
    payload = {
        "operation_key": LITERAL_OPERATION_KEY,
        "objective": "Implement the assigned bounded deliverable and return evidence.",
        "department": "executive-infrastructure",
        "priority": 10,
        "execution_profile": "research_only",
    }
    payload.update(overrides)
    return payload


def _submit_bytes(
    *, observed_grounding: dict[str, Any], request: dict[str, Any], schema: str | None = None,
    **extra_top: Any,
) -> bytes:
    frame: dict[str, Any] = {
        "schema": schema if schema is not None else ceo_ingress.SUBMIT_SCHEMA,
        "observed_grounding": observed_grounding,
        "request": request,
    }
    frame.update(extra_top)
    return (json.dumps(frame) + "\n").encode("utf-8")


def _status_bytes(*, intent_id: Any, schema: str | None = None, **extra_top: Any) -> bytes:
    frame: dict[str, Any] = {
        "schema": schema if schema is not None else ceo_ingress.STATUS_SCHEMA,
        "intent_id": intent_id,
    }
    frame.update(extra_top)
    return (json.dumps(frame) + "\n").encode("utf-8")


def _service_with_ingress(
    tmp_path: Path,
    *,
    socket_root: Path,
    grounding: Any,
    armed: bool = True,
    service_state: str = "READY",
    peer_uid: int | None = None,
    ceo_ingress_socket_path: Path | None = None,
    ceo_ingress_activated_socket: socket.socket | None = None,
) -> ExecutiveControlService:
    config = _config(tmp_path, socket_root=socket_root)

    def factory(_runtime: Runtime) -> _FakeSupervisor:
        return _FakeSupervisor()

    return ExecutiveControlService(
        config,
        supervisor_factory=factory,
        service_state=service_state,
        ceo_ingress_socket_path=(
            ceo_ingress_socket_path
            if ceo_ingress_socket_path is not None
            else socket_root / "ceo-ingress.sock"
        ),
        ceo_ingress_peer_uid=peer_uid if peer_uid is not None else os.geteuid(),
        ceo_ingress_grounding_provider=grounding,
        ceo_ingress_armed=armed,
        ceo_ingress_activated_socket=ceo_ingress_activated_socket,
    )


async def _raw_ceo_request(path: Path, raw: bytes) -> dict[str, Any] | None:
    reader, writer = await asyncio.open_unix_connection(str(path))
    try:
        writer.write(raw)
        await writer.drain()
        try:
            writer.write_eof()
        except (OSError, NotImplementedError):
            pass
        response = await reader.readline()
        if not response:
            return None
        return json.loads(response)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


async def _submit(path: Path, *, observed_grounding=None, request=None, **extra) -> dict:
    return await _raw_ceo_request(
        path,
        _submit_bytes(
            observed_grounding=observed_grounding if observed_grounding is not None else GROUNDING_A,
            request=request if request is not None else _research_request(),
            **extra,
        ),
    )


async def _status(path: Path, intent_id: str, **extra) -> dict:
    return await _raw_ceo_request(path, _status_bytes(intent_id=intent_id, **extra))


def run(coro):
    return asyncio.run(coro)


async def _wait_until(predicate, *, timeout: float = 2.0) -> None:
    """Poll ``predicate()`` until true, instead of asserting on it immediately.

    NIT 15c: the client side of ``_raw_ceo_request`` only awaits the response
    LINE; the server-side handler's own ``finally`` (writer close/drain, THEN
    the §14.1 task-set discard) can still be mid-flight on the event loop the
    instant the client resumes. Asserting immediately after a round trip
    races that cleanup. This gives the loop real (bounded) time to finish it
    instead of asserting on a timing accident.
    """

    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            assert predicate()  # re-assert to raise with a useful message
            return
        await asyncio.sleep(0.01)


# ===========================================================================
# §17.1 peer/protocol
# ===========================================================================


def test_wrong_peer_uid_refuses_before_business_access(tmp_path, short_socket_root):
    async def exercise():
        grounding = _FakeGrounding()
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=grounding,
            peer_uid=os.geteuid() + 1,
        )
        await service.start()
        try:
            response = await _submit(service.ceo_ingress_socket_path)
            assert response["ok"] is False
            assert response["error"]["code"] == "peer_denied"
            assert grounding.calls == 0
            assert service.runtime.jobs.list_jobs() == []
        finally:
            await service.close()

    run(exercise())


def test_missing_kernel_peer_credentials_fail_closed_before_body_read(
    tmp_path, short_socket_root, monkeypatch
):
    async def exercise():
        grounding = _FakeGrounding()
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=grounding
        )
        await service.start()
        try:
            monkeypatch.setattr(
                "control_plane.executive_service._peer_uid", lambda _connection: None
            )
            response = await _submit(service.ceo_ingress_socket_path)
            assert response["ok"] is False
            assert response["error"]["code"] == "peer_credentials_unavailable"
            assert grounding.calls == 0
        finally:
            await service.close()

    run(exercise())


def test_ceo_ingress_path_same_as_operator_path_refuses_at_construction(
    tmp_path, short_socket_root
):
    config = _config(tmp_path, socket_root=short_socket_root)

    def factory(_runtime):
        return _FakeSupervisor()

    with pytest.raises(ValueError, match="must differ from the Operator socket_path"):
        ExecutiveControlService(
            config,
            supervisor_factory=factory,
            ceo_ingress_socket_path=config.socket_path,
            ceo_ingress_peer_uid=os.geteuid(),
            ceo_ingress_grounding_provider=_FakeGrounding(),
        )


def test_wrong_family_activated_socket_refuses_at_construction(tmp_path, short_socket_root):
    config = _config(tmp_path, socket_root=short_socket_root)

    def factory(_runtime):
        return _FakeSupervisor()

    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(ValueError, match="AF_UNIX"):
            ExecutiveControlService(
                config,
                supervisor_factory=factory,
                ceo_ingress_socket_path=short_socket_root / "ceo-ingress.sock",
                ceo_ingress_peer_uid=os.geteuid(),
                ceo_ingress_grounding_provider=_FakeGrounding(),
                ceo_ingress_activated_socket=tcp,
            )
    finally:
        tcp.close()


def test_wrong_bound_activated_socket_refuses_at_construction(tmp_path, short_socket_root):
    config = _config(tmp_path, socket_root=short_socket_root)

    def factory(_runtime):
        return _FakeSupervisor()

    wrong_path = short_socket_root / "wrong.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(wrong_path))
    listener.listen(1)
    try:
        with pytest.raises(ValueError, match="does not match"):
            ExecutiveControlService(
                config,
                supervisor_factory=factory,
                ceo_ingress_socket_path=short_socket_root / "ceo-ingress.sock",
                ceo_ingress_peer_uid=os.geteuid(),
                ceo_ingress_grounding_provider=_FakeGrounding(),
                ceo_ingress_activated_socket=listener,
            )
    finally:
        listener.close()


def test_malformed_utf8_and_invalid_json_yield_zero_job(tmp_path, short_socket_root):
    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        await service.start()
        try:
            bad_utf8 = await _raw_ceo_request(
                service.ceo_ingress_socket_path, b"\xff\xfe\n"
            )
            assert bad_utf8["error"]["code"] == "invalid_json"

            bad_json = await _raw_ceo_request(
                service.ceo_ingress_socket_path, b"{not-json}\n"
            )
            assert bad_json["error"]["code"] == "invalid_json"
            assert service.runtime.jobs.list_jobs() == []
        finally:
            await service.close()

    run(exercise())


def test_oversize_request_yields_zero_job(tmp_path, short_socket_root):
    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        await service.start()
        try:
            oversized = await _raw_ceo_request(
                service.ceo_ingress_socket_path,
                b"x" * (ceo_ingress.MAX_REQUEST_BYTES + 100) + b"\n",
            )
            assert oversized["error"]["code"] == "request_too_large"
            assert service.runtime.jobs.list_jobs() == []
        finally:
            await service.close()

    run(exercise())


def test_missing_newline_eof_partial_frame_yields_zero_job(tmp_path, short_socket_root):
    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        await service.start()
        try:
            # A COMPLETE, parseable JSON value with NO trailing newline must
            # still refuse (§7.3): EOF before newline is an incomplete frame
            # even though the bytes alone would parse.
            complete_but_unterminated = json.dumps(
                {"schema": ceo_ingress.STATUS_SCHEMA, "intent_id": "slack-" + "a" * 32}
            ).encode("utf-8")
            response = await _raw_ceo_request(
                service.ceo_ingress_socket_path, complete_but_unterminated
            )
            assert response["error"]["code"] == "invalid_json"
            assert service.runtime.jobs.list_jobs() == []
        finally:
            await service.close()

    run(exercise())


def test_unknown_schema_refuses(tmp_path, short_socket_root):
    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        await service.start()
        try:
            response = await _status(
                service.ceo_ingress_socket_path,
                "slack-" + "a" * 32,
                schema="mastermind.executive_ceo_ingress_status.v2",
            )
            assert response["error"]["code"] == "unsupported_ingress_schema"
        finally:
            await service.close()

    run(exercise())


def test_extra_or_missing_top_level_keys_refuse(tmp_path, short_socket_root):
    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        await service.start()
        try:
            extra = await _submit(
                service.ceo_ingress_socket_path, unexpected_field="not allowed"
            )
            assert extra["error"]["code"] == "invalid_input"

            missing = await _raw_ceo_request(
                service.ceo_ingress_socket_path,
                (json.dumps({"schema": ceo_ingress.SUBMIT_SCHEMA}) + "\n").encode("utf-8"),
            )
            assert missing["error"]["code"] == "invalid_input"
            assert service.runtime.jobs.list_jobs() == []
        finally:
            await service.close()

    run(exercise())


def test_second_frame_on_one_connection_never_processed(tmp_path, short_socket_root):
    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        await service.start()
        try:
            reader, writer = await asyncio.open_unix_connection(
                str(service.ceo_ingress_socket_path)
            )
            try:
                writer.write(_submit_bytes(observed_grounding=GROUNDING_A, request=_research_request()))
                writer.write(_status_bytes(intent_id="slack-" + "a" * 32))
                await writer.drain()
                first = json.loads(await reader.readline())
                assert first["ok"] is True
                # The handler closes after ONE response; a second frame queued
                # on the same connection is never read/processed.
                remainder = await asyncio.wait_for(reader.read(), timeout=1)
                assert remainder == b""
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass
            assert len(service.runtime.jobs.list_jobs()) == 1
        finally:
            await service.close()

    run(exercise())


def test_generic_dispatch_request_monkeypatched_to_explode_ingress_still_works(
    tmp_path, short_socket_root, monkeypatch
):
    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        await service.start()
        try:
            async def boom(*_args, **_kwargs):
                raise AssertionError("generic Operator dispatcher must never be reached")

            monkeypatch.setattr(service, "_dispatch_request", boom)
            response = await _submit(service.ceo_ingress_socket_path)
            assert response["ok"] is True
        finally:
            await service.close()

    run(exercise())


# ===========================================================================
# §17.2 privilege/schema
# ===========================================================================


@pytest.mark.parametrize(
    "field,value",
    [
        ("actor", "someone-else"),
        ("requested_authorities", ["MERGE"]),
        ("branch", "codex/evil"),
        ("worktree", "/etc"),
        ("provider", "anthropic"),
        ("model", "claude"),
        ("credential", "x"),
        ("intent_kind", "review"),
        ("business_impact", "critical"),
        ("service_control", "restart"),
    ],
)
def test_privileged_caller_fields_refuse(tmp_path, short_socket_root, field, value):
    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        await service.start()
        try:
            response = await _submit(
                service.ceo_ingress_socket_path,
                request=_research_request(**{field: value}),
            )
            assert response["ok"] is False
            assert response["error"]["code"] == "invalid_input"
            assert service.runtime.jobs.list_jobs() == []
        finally:
            await service.close()

    run(exercise())


@pytest.mark.parametrize(
    "bad_id",
    [
        "mcp-400560e76b2e72590f12d30f782bfc4d",  # MCP namespace, not Slack
        "JOB-001",
        "SLACK-" + "a" * 32,  # uppercase prefix
        "slack-" + "a" * 31,  # too short
        "slack-" + "a" * 33,  # too long
        "slack-" + "g" * 32,  # non-hex
        "not-a-real-id",
    ],
)
def test_status_rejects_non_slack_ids_before_lookup(tmp_path, short_socket_root, bad_id):
    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        await service.start()
        try:
            response = await _status(service.ceo_ingress_socket_path, bad_id)
            assert response["ok"] is False
            assert response["error"]["code"] == "invalid_intent_id"
        finally:
            await service.close()

    run(exercise())


def test_status_absent_valid_slack_id_returns_true_not_found(tmp_path, short_socket_root):
    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        await service.start()
        try:
            response = await _status(service.ceo_ingress_socket_path, "slack-" + "0" * 32)
            assert response["ok"] is False
            assert response["error"]["code"] == "not_found"
        finally:
            await service.close()

    run(exercise())


# ===========================================================================
# §17.3 grounding/replay
# ===========================================================================


def test_malformed_observed_grounding_refuses_before_provider(tmp_path, short_socket_root):
    async def exercise():
        grounding = _FakeGrounding()
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=grounding
        )
        await service.start()
        try:
            response = await _submit(
                service.ceo_ingress_socket_path,
                observed_grounding={"mastermind_sha": "not-hex", "macro_sha": GROUNDING_A["macro_sha"], "boot_packet_schema": ceo_ingress.BOOT_PACKET_SCHEMA},
            )
            assert response["ok"] is False
            assert response["error"]["code"] == "invalid_input"
            assert grounding.calls == 0
        finally:
            await service.close()

    run(exercise())


def test_trusted_provider_unavailable_yields_zero_job(tmp_path, short_socket_root):
    async def exercise():
        grounding = _FakeGrounding(error=RuntimeError("boom"))
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=grounding
        )
        await service.start()
        try:
            response = await _submit(service.ceo_ingress_socket_path)
            assert response["ok"] is False
            assert response["error"]["code"] == "grounding_unavailable"
            assert service.runtime.jobs.list_jobs() == []
        finally:
            await service.close()

    run(exercise())


def test_trusted_provider_malformed_output_yields_zero_job(tmp_path, short_socket_root):
    async def exercise():
        grounding = _FakeGrounding(sequence=[{"mastermind_sha": "short"}])
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=grounding
        )
        await service.start()
        try:
            response = await _submit(service.ceo_ingress_socket_path)
            assert response["ok"] is False
            assert response["error"]["code"] == "grounding_unavailable"
            assert service.runtime.jobs.list_jobs() == []
        finally:
            await service.close()

    run(exercise())


def test_observed_mismatch_trusted_yields_grounding_mismatch(tmp_path, short_socket_root):
    async def exercise():
        grounding = _FakeGrounding(sequence=[GROUNDING_B])
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=grounding
        )
        await service.start()
        try:
            response = await _submit(service.ceo_ingress_socket_path, observed_grounding=GROUNDING_A)
            assert response["ok"] is False
            assert response["error"]["code"] == "grounding_mismatch"
            assert service.runtime.jobs.list_jobs() == []
        finally:
            await service.close()

    run(exercise())


def test_grounding_moves_between_observe_and_resubmit_yields_grounding_changed(
    tmp_path, short_socket_root
):
    async def exercise():
        # Both caller-observed and the FIRST trusted read agree (GROUNDING_A);
        # the SECOND trusted read (immediately before the first canonical
        # submit) has moved to GROUNDING_B.
        grounding = _FakeGrounding(sequence=[GROUNDING_A, GROUNDING_B])
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=grounding
        )
        await service.start()
        try:
            response = await _submit(service.ceo_ingress_socket_path, observed_grounding=GROUNDING_A)
            assert response["ok"] is False
            assert response["error"]["code"] == "grounding_changed"
            assert grounding.calls == 2
            assert service.runtime.jobs.list_jobs() == []
        finally:
            await service.close()

    run(exercise())


def test_committed_same_fingerprint_reconciles_without_grounding_call(
    tmp_path, short_socket_root
):
    async def exercise():
        grounding = _FakeGrounding(sequence=[GROUNDING_A])
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=grounding
        )
        await service.start()
        try:
            first = await _submit(service.ceo_ingress_socket_path, observed_grounding=GROUNDING_A)
            assert first["ok"] is True
            assert first["result"]["duplicate"] is False
            calls_after_first = grounding.calls
            assert calls_after_first == 2  # first observe + pre-submit re-observe

            # Trusted grounding has since moved organizationally; the SAME
            # operation replayed with the ORIGINAL claim must still reconcile
            # to the canonical duplicate receipt with NO current-grounding
            # requirement at all (existing durable event resolved BEFORE any
            # grounding-provider call).
            grounding._sequence = [GROUNDING_B]
            second = await _submit(service.ceo_ingress_socket_path, observed_grounding=GROUNDING_A)
            assert second["ok"] is True
            assert second["result"]["duplicate"] is True
            assert second["result"]["job_id"] == first["result"]["job_id"]
            assert grounding.calls == calls_after_first  # untouched
            assert len(service.runtime.jobs.list_jobs()) == 1
        finally:
            await service.close()

    run(exercise())


def test_committed_changed_fingerprint_yields_operation_conflict(tmp_path, short_socket_root):
    async def exercise():
        grounding = _FakeGrounding(sequence=[GROUNDING_A])
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=grounding
        )
        await service.start()
        try:
            first = await _submit(service.ceo_ingress_socket_path, observed_grounding=GROUNDING_A)
            assert first["ok"] is True

            grounding._sequence = [GROUNDING_A]
            conflicting = await _submit(
                service.ceo_ingress_socket_path,
                observed_grounding=GROUNDING_A,
                request=_research_request(objective="A materially different objective text."),
            )
            assert conflicting["ok"] is False
            assert conflicting["error"]["code"] == "operation_conflict"
            assert len(service.runtime.jobs.list_jobs()) == 1
        finally:
            await service.close()

    run(exercise())


def test_corrupted_durable_event_is_backend_refused_not_not_found(
    tmp_path, short_socket_root, monkeypatch
):
    async def exercise():
        grounding = _FakeGrounding(sequence=[GROUNDING_A])
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=grounding
        )
        await service.start()
        try:
            first = await _submit(service.ceo_ingress_socket_path, observed_grounding=GROUNDING_A)
            assert first["ok"] is True
            intent_id = first["result"]["intent_id"]

            def corrupt_resolve(_runtime, _intent_id):
                raise ceo_intent.CeoIntentError("forced corruption for test")

            monkeypatch.setattr(ceo_intent, "resolve_intent", corrupt_resolve)
            status = await _status(service.ceo_ingress_socket_path, intent_id)
            assert status["ok"] is False
            assert status["error"]["code"] == "backend_refused"
            # MAJOR 5: literal, never read from the module's own dict — a
            # mutation that changes the dict value must not silently drag the
            # test's expectation along with it.
            assert status["error"]["message"] == "Executive CEO ingress backend refused the request"
        finally:
            await service.close()

    run(exercise())


def test_concurrent_identical_winner_yields_exactly_one_job_and_duplicate(
    tmp_path, short_socket_root, monkeypatch
):
    async def exercise():
        grounding = _FakeGrounding(sequence=[GROUNDING_A])
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=grounding
        )
        await service.start()
        try:
            real_submit_intent = ceo_intent.submit_intent
            state = {"raced": False}

            def racing_submit_intent(runtime, payload, *, workspace_root=None):
                if not state["raced"]:
                    state["raced"] = True
                    # A sibling caller committed the SAME operation between our
                    # pre-check and our own submit attempt.
                    real_submit_intent(runtime, payload, workspace_root=workspace_root)
                    raise ceo_intent.CeoIntentError("simulated race: sibling committed first")
                return real_submit_intent(runtime, payload, workspace_root=workspace_root)

            monkeypatch.setattr(ceo_intent, "submit_intent", racing_submit_intent)
            response = await _submit(service.ceo_ingress_socket_path, observed_grounding=GROUNDING_A)
            assert response["ok"] is True
            assert response["result"]["duplicate"] is True
            assert len(service.runtime.jobs.list_jobs()) == 1
        finally:
            await service.close()

    run(exercise())


def test_concurrent_conflicting_winner_yields_one_job_and_operation_conflict(
    tmp_path, short_socket_root, monkeypatch
):
    async def exercise():
        grounding = _FakeGrounding(sequence=[GROUNDING_A])
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=grounding
        )
        await service.start()
        try:
            real_submit_intent = ceo_intent.submit_intent
            state = {"raced": False}

            def racing_submit_intent(runtime, payload, *, workspace_root=None):
                if not state["raced"]:
                    state["raced"] = True
                    conflicting = dict(payload)
                    conflicting["objective"] = "A sibling committed a DIFFERENT objective first."
                    real_submit_intent(runtime, conflicting, workspace_root=workspace_root)
                    raise ceo_intent.CeoIntentError("simulated race: sibling committed a conflict")
                return real_submit_intent(runtime, payload, workspace_root=workspace_root)

            monkeypatch.setattr(ceo_intent, "submit_intent", racing_submit_intent)
            response = await _submit(service.ceo_ingress_socket_path, observed_grounding=GROUNDING_A)
            assert response["ok"] is False
            assert response["error"]["code"] == "operation_conflict"
            assert len(service.runtime.jobs.list_jobs()) == 1
        finally:
            await service.close()

    run(exercise())


def test_frozen_slack_vector_matches_literal_regression(tmp_path, short_socket_root):
    """§6.2/§15.1 — the literal frozen Slack intent id, proven end-to-end
    through the wire, not merely unit-computed."""

    async def exercise():
        grounding = _FakeGrounding(sequence=[GROUNDING_A])
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=grounding
        )
        await service.start()
        try:
            response = await _submit(
                service.ceo_ingress_socket_path,
                observed_grounding=GROUNDING_A,
                request=_research_request(operation_key=LITERAL_OPERATION_KEY),
            )
            assert response["ok"] is True
            assert response["result"]["intent_id"] == LITERAL_SLACK_INTENT_ID
        finally:
            await service.close()

    run(exercise())


# ===========================================================================
# §17.4 readiness/lifecycle
# ===========================================================================


def test_unarmed_ingress_refuses_while_operator_unaffected(tmp_path, short_socket_root):
    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding(), armed=False
        )
        await service.start()
        try:
            response = await _submit(service.ceo_ingress_socket_path)
            assert response["ok"] is False
            assert response["error"]["code"] == "ingress_unavailable"

            from control_plane.executive_service import send_control_request

            status = await send_control_request(service.socket_path, "status")
            assert status["ok"] is True
        finally:
            await service.close()

    run(exercise())


def test_armed_awaiting_canary_ingress_works_operator_mutation_still_refuses(
    tmp_path, short_socket_root
):
    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding(),
            armed=True, service_state="AWAITING_CANARY",
        )
        await service.start()
        try:
            response = await _submit(service.ceo_ingress_socket_path)
            assert response["ok"] is True

            from control_plane.executive_service import send_control_request

            mutation = await send_control_request(service.socket_path, "workers")
            assert mutation["ok"] is False
            assert "AWAITING_CANARY" in mutation["error"]["message"]
        finally:
            await service.close()

    run(exercise())


def test_dynamic_quarantined_state_refuses_ingress(tmp_path, short_socket_root):
    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        await service.start()
        try:
            service._service_state = "QUARANTINED"
            response = await _submit(service.ceo_ingress_socket_path)
            assert response["ok"] is False
            assert response["error"]["code"] == "ingress_unavailable"
        finally:
            await service.close()

    run(exercise())


def test_unknown_future_service_state_refuses_ingress(tmp_path, short_socket_root):
    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        await service.start()
        try:
            service._service_state = "SOME_FUTURE_STATE"
            response = await _submit(service.ceo_ingress_socket_path)
            assert response["ok"] is False
            assert response["error"]["code"] == "ingress_unavailable"
        finally:
            await service.close()

    run(exercise())


def test_valid_submit_creates_zero_attempts_zero_workers(tmp_path, short_socket_root):
    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        await service.start()
        try:
            response = await _submit(service.ceo_ingress_socket_path)
            assert response["ok"] is True
            assert response["result"]["dispatched"] is False
            assert service.runtime.attempts.list_attempts() == []
            assert service.runtime.workers.list_workers() == []
            assert len(service.runtime.jobs.list_jobs()) == 1
        finally:
            await service.close()

    run(exercise())


def test_listener_startup_partial_failure_rolls_back_and_is_restartable(
    tmp_path, short_socket_root, monkeypatch
):
    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        started_ceo_ingress = asyncio.Event()

        real_start_ceo_ingress = service._start_ceo_ingress_serving

        async def observing_start_ceo_ingress():
            await real_start_ceo_ingress()
            started_ceo_ingress.set()

        async def failing_start_operator():
            raise RuntimeError("simulated Operator start_serving failure")

        monkeypatch.setattr(service, "_start_ceo_ingress_serving", observing_start_ceo_ingress)
        monkeypatch.setattr(service, "_start_operator_serving", failing_start_operator)

        with pytest.raises(RuntimeError, match="simulated Operator start_serving failure"):
            await service.start()

        assert started_ceo_ingress.is_set()
        assert service.ceo_ingress_ready is False
        assert not service.running_marker_path.exists()
        assert not service.ceo_ingress_socket_path.exists()
        assert not service.socket_path.exists()

        # A fresh instance can now start cleanly under the same single lock.
        fresh = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        await fresh.start()
        try:
            assert fresh.ceo_ingress_ready is True
            response = await _submit(fresh.ceo_ingress_socket_path)
            assert response["ok"] is True
        finally:
            await fresh.close()

    run(exercise())


def test_racing_ingress_request_during_operator_start_failure_gets_only_ingress_unavailable(
    tmp_path, short_socket_root, monkeypatch
):
    """R1 §2.2 — if CeoIngress begins serving but Operator's start_serving()
    then fails, a request racing that narrow window gets only
    ``ingress_unavailable`` and creates zero Job, calls zero grounding
    provider, and reaches no generic dispatcher."""

    async def exercise():
        grounding = _FakeGrounding()
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=grounding
        )
        race_response: dict[str, Any] = {}

        async def failing_start_operator():
            race_response["value"] = await _submit(service.ceo_ingress_socket_path)
            raise RuntimeError("simulated Operator start_serving failure")

        monkeypatch.setattr(service, "_start_operator_serving", failing_start_operator)

        with pytest.raises(RuntimeError, match="simulated Operator start_serving failure"):
            await service.start()

        assert race_response["value"]["ok"] is False
        assert race_response["value"]["error"]["code"] == "ingress_unavailable"
        assert grounding.calls == 0

    run(exercise())


def test_close_twice_is_safe(tmp_path, short_socket_root):
    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        await service.start()
        await service.close()
        await service.close()  # idempotent

    run(exercise())


def test_normal_ingress_handler_leaves_no_task_set_residue(tmp_path, short_socket_root):
    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        await service.start()
        try:
            response = await _submit(service.ceo_ingress_socket_path)
            assert response["ok"] is True
            # NIT 15c: deterministic instead of timing-dependent -- poll
            # briefly for quiescence rather than asserting the instant the
            # client's own read completes (see ``_wait_until``).
            await _wait_until(lambda: service._ceo_ingress_tasks == set())
            assert service._ceo_ingress_tasks == set()
        finally:
            await service.close()

    run(exercise())


def test_marker_exists_pre_listeners_but_grants_no_admission_and_blocks_second_instance(
    tmp_path, short_socket_root, monkeypatch
):
    """R2 §4 — the existing running marker is created (via ``_prepare_socket``/
    ``_acquire_service_lock``, UNCHANGED) before Runtime/listener startup, as
    current source already does.  That fact alone does not make
    ``startup_ready`` true and does not allow CeoIngress admission; a second
    instance cannot acquire the service lock during this window; and once
    startup completes, ``_started_at``/the ingress latch are both set."""

    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        loop = asyncio.get_running_loop()
        entered = asyncio.Event()
        release = asyncio.Event()

        def paused_reconcile(self, *, requeue_lost: bool = False):
            loop.call_soon_threadsafe(entered.set)
            fut = asyncio.run_coroutine_threadsafe(release.wait(), loop)
            fut.result()
            return []

        monkeypatch.setattr(_FakeSupervisor, "reconcile_restart", paused_reconcile)

        start_task = asyncio.create_task(service.start())
        await asyncio.wait_for(entered.wait(), timeout=2)

        # Lock/marker already acquired synchronously by _prepare_socket()
        # BEFORE this paused point -- but neither listener has been
        # constructed yet, and the startup latch is still false: no
        # admission is possible from this fact alone.
        assert service.running_marker_path.is_file()
        assert service.service_lock_path.is_file()
        assert service.ceo_ingress_ready is False
        assert service._server is None
        assert service._ceo_ingress_server is None

        # A second instance cannot acquire the service lock during this
        # startup window.
        second = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        with pytest.raises(Exception, match="holds the socket lock"):
            await second.start()

        release.set()
        await asyncio.wait_for(start_task, timeout=2)
        try:
            assert service.ceo_ingress_ready is True
            assert service._started_at is not None
        finally:
            await service.close()

    run(exercise())


def test_no_request_can_alter_startup_latch(tmp_path, short_socket_root):
    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        await service.start()
        try:
            assert service.ceo_ingress_ready is True
            await _submit(service.ceo_ingress_socket_path)
            await _status(service.ceo_ingress_socket_path, "slack-" + "0" * 32)
            assert service.ceo_ingress_ready is True
        finally:
            await service.close()

    run(exercise())


# ===========================================================================
# §17.5 timeout/disconnect/drain
# ===========================================================================


def test_paused_submit_survives_client_disconnect_and_close_holds_lock_until_terminal(
    tmp_path, short_socket_root, monkeypatch
):
    async def exercise():
        grounding = _FakeGrounding(sequence=[GROUNDING_A])
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=grounding
        )
        await service.start()

        loop = asyncio.get_running_loop()
        entered = asyncio.Event()
        release = asyncio.Event()
        real_submit_intent = ceo_intent.submit_intent

        def paused_submit_intent(runtime, payload, *, workspace_root=None):
            # Runs inside asyncio.to_thread's worker thread.  Emulate "paused
            # AFTER the sync thread invocation" by blocking this thread on a
            # threadsafe wait for the event-loop-side release signal.
            loop.call_soon_threadsafe(entered.set)
            fut = asyncio.run_coroutine_threadsafe(release.wait(), loop)
            fut.result()
            return real_submit_intent(runtime, payload, workspace_root=workspace_root)

        monkeypatch.setattr(ceo_intent, "submit_intent", paused_submit_intent)

        reader, writer = await asyncio.open_unix_connection(str(service.ceo_ingress_socket_path))
        writer.write(_submit_bytes(observed_grounding=GROUNDING_A, request=_research_request()))
        await writer.drain()
        await asyncio.wait_for(entered.wait(), timeout=2)

        # BLOCKER 1 (7a): the live handler task is tracked in the §14.1
        # drain set WHILE the canonical mutation is paused mid-flight -- a
        # proof independent of ``Server.wait_closed()`` semantics.
        assert len(service._ceo_ingress_tasks) == 1

        # Disconnect the client while the mutation is paused mid-flight.
        writer.close()
        try:
            await writer.wait_closed()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

        # Trigger service close while submit is paused: listeners stop
        # accepting, but close() must NOT release the lock/marker until this
        # admission reaches a real terminal outcome.
        close_task = asyncio.create_task(service.close())
        await asyncio.sleep(0.05)
        assert not close_task.done()
        assert service.running_marker_path.exists()

        release.set()
        await asyncio.wait_for(close_task, timeout=2)

        assert not service.running_marker_path.exists()
        jobs = service.runtime.jobs.list_jobs()
        assert len(jobs) == 1  # committed exactly once despite the disconnect

        # After terminal drain, a fresh service can restart cleanly and its
        # dedicated status readback recovers the exact canonical receipt (no
        # second Job was ever created).
        fresh = _service_with_ingress(
            tmp_path, socket_root=short_socket_root,
            grounding=_FakeGrounding(sequence=[GROUNDING_A]),
        )
        await fresh.start()
        try:
            status = await _status(fresh.ceo_ingress_socket_path, LITERAL_SLACK_INTENT_ID)
            assert status["ok"] is True
            assert status["result"]["job_id"] == jobs[0].job_id
            assert len(fresh.runtime.jobs.list_jobs()) == 1
        finally:
            await fresh.close()

    run(exercise())


# ===========================================================================
# §17.6 error containment
# ===========================================================================


def test_downstream_authority_denial_yields_authority_refused_zero_job(
    tmp_path, short_socket_root, monkeypatch
):
    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        await service.start()
        try:
            def forced_denial(*_args, **_kwargs):
                raise AuthorityDenied("forced test denial")

            monkeypatch.setattr(
                "control_plane.executive_runtime.ExecutiveAuthorityPolicy.load",
                forced_denial,
            )
            response = await _submit(service.ceo_ingress_socket_path)
            assert response["ok"] is False
            assert response["error"]["code"] == "authority_refused"
            # MAJOR 5: literal, not a self-referential dict lookup.
            assert response["error"]["message"] == (
                "the requested execution authority was refused"
            )
            assert "forced test denial" not in json.dumps(response)
            assert service.runtime.jobs.list_jobs() == []
        finally:
            await service.close()

    run(exercise())


def test_successful_receipt_claiming_dispatched_true_is_never_presented_as_success(
    tmp_path, short_socket_root, monkeypatch
):
    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        await service.start()
        try:
            real_submit_intent = ceo_intent.submit_intent

            def lying_submit_intent(runtime, payload, *, workspace_root=None):
                receipt = real_submit_intent(runtime, payload, workspace_root=workspace_root)
                receipt["dispatched"] = True  # backend contract defect
                return receipt

            monkeypatch.setattr(ceo_intent, "submit_intent", lying_submit_intent)
            response = await _submit(service.ceo_ingress_socket_path)
            assert response["ok"] is False
            assert response["error"]["code"] == "backend_refused"
        finally:
            await service.close()

    run(exercise())


_FAKE_HOST_PATH = "/Users/operator/private/repo"
_FAKE_PRODUCTION_PATH = "/var/db/mastermind-executive/secret-state"
_FAKE_URL = "https://example.invalid/callback?token=abc123secretvalue"
_FAKE_TOKEN = "sk-ant-fake0000000000000000000000000000000000"
_FAKE_MULTILINE = "line-one\nline-two\x07\x1b[31mcontrol"

_INJECTED_FRAGMENTS = (
    _FAKE_HOST_PATH,
    _FAKE_PRODUCTION_PATH,
    _FAKE_URL,
    _FAKE_TOKEN,
    "line-two",
)


def _forced_exception() -> RuntimeError:
    return RuntimeError(
        f"failure while reading {_FAKE_HOST_PATH} and {_FAKE_PRODUCTION_PATH} "
        f"via {_FAKE_URL} using {_FAKE_TOKEN}\n{_FAKE_MULTILINE}"
    )


def _assert_no_leak(response: dict[str, Any], expected_code: str, expected_message: str) -> None:
    assert response["ok"] is False
    assert response["error"]["code"] == expected_code
    assert response["error"]["message"] == expected_message
    wire = json.dumps(response)
    for fragment in _INJECTED_FRAGMENTS:
        assert fragment not in wire


def test_no_path_no_secret_from_grounding_provider(tmp_path, short_socket_root):
    async def exercise():
        grounding = _FakeGrounding(error=_forced_exception())
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=grounding
        )
        await service.start()
        try:
            response = await _submit(service.ceo_ingress_socket_path)
            # MAJOR 5: literal, not a self-referential dict lookup.
            _assert_no_leak(
                response, "grounding_unavailable",
                "trusted grounding is unavailable",
            )
            # sanitize_external_text alone would NOT have removed the paths —
            # proving this test kills a mutation that forwards it instead of
            # the fixed literal (R1 §3.1/§5).
            sanitized = sanitize_external_text(str(_forced_exception()))
            assert _FAKE_HOST_PATH in sanitized
            assert _FAKE_PRODUCTION_PATH in sanitized
        finally:
            await service.close()

    run(exercise())


def test_no_path_no_secret_from_status_readback_backend(
    tmp_path, short_socket_root, monkeypatch
):
    async def exercise():
        grounding = _FakeGrounding(sequence=[GROUNDING_A])
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=grounding
        )
        await service.start()
        try:
            first = await _submit(service.ceo_ingress_socket_path, observed_grounding=GROUNDING_A)
            assert first["ok"] is True
            intent_id = first["result"]["intent_id"]

            def corrupt_resolve(_runtime, _intent_id):
                raise ceo_intent.CeoIntentError(str(_forced_exception()))

            monkeypatch.setattr(ceo_intent, "resolve_intent", corrupt_resolve)
            response = await _status(service.ceo_ingress_socket_path, intent_id)
            # MAJOR 5: literal, not a self-referential dict lookup.
            _assert_no_leak(
                response, "backend_refused",
                "Executive CEO ingress backend refused the request",
            )
        finally:
            await service.close()

    run(exercise())


def test_no_path_no_secret_from_unexpected_internal_exception(
    tmp_path, short_socket_root, monkeypatch
):
    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        await service.start()
        try:
            def boom(*_args, **_kwargs):
                raise _forced_exception()

            monkeypatch.setattr(ceo_ingress, "handle_frame", boom)
            response = await _submit(service.ceo_ingress_socket_path)
            _assert_no_leak(
                response, "internal_error",
                "Executive CEO ingress failed",
            )
        finally:
            await service.close()

    run(exercise())


# ===========================================================================
# BLOCKER 1 (kills M1) — drain-set proof independent of Server.wait_closed()
# ===========================================================================


def test_close_holds_lock_even_when_server_wait_closed_is_a_no_op(
    tmp_path, short_socket_root, monkeypatch
):
    """BLOCKER 1 (7b) — simulate Python<=3.11 ``Server.wait_closed()``
    semantics (which do NOT wait for already-accepted handler coroutines to
    finish) by monkeypatching the bound ingress ``asyncio.Server.wait_closed``
    instance attribute to return immediately. If ``close()``'s explicit
    ``_ceo_ingress_tasks`` gather (§14.1/§14.2) were ever deleted, ``close()``
    would then return -- and release the lock/marker -- the moment the
    no-op ``wait_closed()`` resolves, while the paused ``submit_intent``
    thread is still running. This test dies under that mutation and passes
    on real code, proving the drain set (not ``Server.wait_closed()``) is
    what actually holds the lock."""

    async def exercise():
        grounding = _FakeGrounding(sequence=[GROUNDING_A])
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=grounding
        )
        await service.start()

        loop = asyncio.get_running_loop()
        entered = asyncio.Event()
        release = asyncio.Event()
        real_submit_intent = ceo_intent.submit_intent

        def paused_submit_intent(runtime, payload, *, workspace_root=None):
            loop.call_soon_threadsafe(entered.set)
            fut = asyncio.run_coroutine_threadsafe(release.wait(), loop)
            fut.result()
            return real_submit_intent(runtime, payload, workspace_root=workspace_root)

        monkeypatch.setattr(ceo_intent, "submit_intent", paused_submit_intent)

        # Make the bound INGRESS server's wait_closed() a no-op -- an instance
        # attribute shadows the class method, so ``close()``'s own
        # ``await ceo_ingress_server.wait_closed()`` call resolves instantly
        # regardless of any still-running handler coroutine.
        async def immediate_wait_closed() -> None:
            return None

        monkeypatch.setattr(
            service._ceo_ingress_server, "wait_closed", immediate_wait_closed
        )

        reader, writer = await asyncio.open_unix_connection(str(service.ceo_ingress_socket_path))
        writer.write(_submit_bytes(observed_grounding=GROUNDING_A, request=_research_request()))
        await writer.drain()
        await asyncio.wait_for(entered.wait(), timeout=2)

        close_task = asyncio.create_task(service.close())
        await asyncio.sleep(0.05)
        # If this fails, the mutation (deleting/bypassing the drain-set
        # gather) has made close() rely on wait_closed() alone -- which we
        # just proved resolves instantly here.
        assert not close_task.done()
        assert service.running_marker_path.exists()

        release.set()
        await asyncio.wait_for(close_task, timeout=2)
        assert not service.running_marker_path.exists()

        writer.close()
        try:
            await writer.wait_closed()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    run(exercise())


# ===========================================================================
# MAJOR 2 — closed error vocabulary literal pin
# ===========================================================================


def test_error_codes_closed_vocabulary_pin():
    """MAJOR 2 — the exact §12 closed error-code set, written as literals so a
    mutation widening/narrowing ``ERROR_CODES`` cannot drag the expectation
    along with it; ``timeout`` and ``request_failed`` (the generic Operator
    code) are explicitly excluded from the dedicated ingress vocabulary."""

    assert ceo_ingress.ERROR_CODES == frozenset(
        {
            "peer_credentials_unavailable",
            "peer_denied",
            "ingress_unavailable",
            "unsupported_ingress_schema",
            "request_too_large",
            "response_too_large",
            "invalid_json",
            "invalid_input",
            "invalid_intent_id",
            "not_found",
            "grounding_unavailable",
            "grounding_mismatch",
            "grounding_changed",
            "operation_conflict",
            "authority_refused",
            "backend_unavailable",
            "backend_refused",
            "internal_error",
        }
    )
    assert "timeout" not in ceo_ingress.ERROR_CODES
    assert "request_failed" not in ceo_ingress.ERROR_CODES


# ===========================================================================
# MAJOR 4 (kills M13) — pre-serving admission + close() latch reset
# ===========================================================================


def test_no_business_processing_before_start_serving(tmp_path, short_socket_root):
    """MAJOR 4a, kills M13 — after ``_bind_ceo_ingress_server`` with
    ``start_serving=False`` but before ``start_serving()`` is ever called, a
    connection attempt is not processed: either the connect itself fails
    (observed on this platform: the listening socket has not yet started
    accepting) or, if the connect succeeds at the OS accept-queue level, no
    response/business processing occurs within a short budget. Either way
    zero grounding-provider calls occur."""

    async def exercise():
        grounding = _FakeGrounding()
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=grounding
        )
        service._prepare_socket()
        try:
            await service._bind_ceo_ingress_server(start_serving=False)
            try:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_unix_connection(str(service.ceo_ingress_socket_path)),
                        timeout=1,
                    )
                except (ConnectionRefusedError, OSError):
                    # The listening socket is not yet accepting connections at
                    # all -- connect itself refuses.  This alone satisfies "a
                    # connection attempt does not get processed."
                    return
                try:
                    writer.write(
                        _submit_bytes(
                            observed_grounding=GROUNDING_A, request=_research_request()
                        )
                    )
                    await writer.drain()
                    with pytest.raises(asyncio.TimeoutError):
                        await asyncio.wait_for(reader.readline(), timeout=0.3)
                finally:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                        pass
            finally:
                server, service._ceo_ingress_server = service._ceo_ingress_server, None
                if server is not None:
                    server.close()
                    await server.wait_closed()
        finally:
            service._release_service_lock()
            assert grounding.calls == 0

    run(exercise())


def test_close_resets_ceo_ingress_ready_and_restarted_instance_gates_fresh(
    tmp_path, short_socket_root
):
    """MAJOR 4b — ``close()`` resets the startup latch to False on a
    NORMALLY-started (not failed-startup) instance, and a freshly
    constructed/started instance begins gated and only becomes ready after
    its OWN ``start()`` completes."""

    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        assert service.ceo_ingress_ready is False
        await service.start()
        assert service.ceo_ingress_ready is True
        await service.close()
        assert service.ceo_ingress_ready is False

        fresh = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        assert fresh.ceo_ingress_ready is False
        await fresh.start()
        try:
            assert fresh.ceo_ingress_ready is True
        finally:
            await fresh.close()
        assert fresh.ceo_ingress_ready is False

    run(exercise())


# ===========================================================================
# MINOR 8 (kills M7) — oversize canonical receipt refuses, never truncated
# ===========================================================================


def test_oversized_receipt_refuses_response_too_large_never_truncated_forwarded(
    tmp_path, short_socket_root, monkeypatch
):
    """MINOR 8, kills M7 — a canonical receipt that would blow the dedicated
    ingress's 32 KiB wire ceiling (§7.4) refuses with the fixed
    ``response_too_large`` shape; the oversized content itself must never
    reach the wire, truncated or otherwise."""

    async def exercise():
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=_FakeGrounding()
        )
        await service.start()
        try:
            real_submit_intent = ceo_intent.submit_intent
            marker = "OVERSIZED-PAYLOAD-" + ("x" * 40000)

            def bloated_submit_intent(runtime, payload, *, workspace_root=None):
                receipt = dict(
                    real_submit_intent(runtime, payload, workspace_root=workspace_root)
                )
                receipt["_bloat"] = marker
                return receipt

            monkeypatch.setattr(ceo_intent, "submit_intent", bloated_submit_intent)
            response = await _submit(service.ceo_ingress_socket_path)
            assert response["ok"] is False
            assert response["error"]["code"] == "response_too_large"
            assert response["error"]["message"] == "response exceeds byte limit"
            wire = json.dumps(response)
            assert marker not in wire
            assert "_bloat" not in wire
        finally:
            await service.close()

    run(exercise())


# ===========================================================================
# MINOR 9 (kills M9) — duplicate reconciliation MUST call the real sink
# ===========================================================================


def test_committed_same_fingerprint_reconciliation_calls_submit_intent(
    tmp_path, short_socket_root, monkeypatch
):
    """MINOR 9, kills M9 — §11.2 step 5's reconciliation on the duplicate path
    MUST call the existing v1 sink (``ceo_intent.submit_intent``) again to
    obtain the canonical duplicate receipt; a mutation that short-circuits the
    sink (fabricating ``duplicate=True`` without calling it) is caught here."""

    async def exercise():
        grounding = _FakeGrounding(sequence=[GROUNDING_A])
        service = _service_with_ingress(
            tmp_path, socket_root=short_socket_root, grounding=grounding
        )
        await service.start()
        try:
            first = await _submit(service.ceo_ingress_socket_path, observed_grounding=GROUNDING_A)
            assert first["ok"] is True

            real_submit_intent = ceo_intent.submit_intent
            calls = {"count": 0}

            def spy_submit_intent(runtime, payload, *, workspace_root=None):
                calls["count"] += 1
                return real_submit_intent(runtime, payload, workspace_root=workspace_root)

            monkeypatch.setattr(ceo_intent, "submit_intent", spy_submit_intent)
            # Trusted grounding has since moved; irrelevant to reconciliation
            # (the durable event resolves BEFORE any grounding-provider call).
            grounding._sequence = [GROUNDING_B]
            second = await _submit(service.ceo_ingress_socket_path, observed_grounding=GROUNDING_A)
            assert second["ok"] is True
            assert second["result"]["duplicate"] is True
            assert calls["count"] == 1
        finally:
            await service.close()

    run(exercise())


# ===========================================================================
# MINOR 13 — boot packet schema equality pin (never an import in the module)
# ===========================================================================


def test_boot_packet_schema_matches_ceo_boot_packet_constant():
    """MINOR 13 — equality pin only.  ``control_plane.executive_ceo_ingress``
    keeps its OWN literal ``BOOT_PACKET_SCHEMA`` and must never import
    ``control_plane.ceo_boot_packet`` itself (verified by the module's own
    import list, not re-checked here); the import happens in THIS TEST only,
    to prove the two literals still agree."""

    from control_plane import ceo_boot_packet

    assert ceo_ingress.BOOT_PACKET_SCHEMA == ceo_boot_packet.SCHEMA
