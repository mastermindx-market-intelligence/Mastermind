"""Refusal observability for Executive OS acceptance control commands.

A privileged Phase 1C acceptance run reached ``create-proof-job`` and failed
with nothing but ``control command create-proof-job failed with exit 2``: the
operator CLI had printed the service's structured envelope
(``{"ok": false, "error": {"code": ..., "message": ...}}``) to stdout, and
``_run(check=True)`` raised on the exit code and discarded it.

These tests pin three things:

* the bounded, sanitized, redacted refusal reason now rides on that failure;
* ``_run`` itself is unchanged: no acceptance command dumps stderr broadly;
* a client that disconnects while the service is delivering an error envelope
  cannot produce an unhandled exception or wedge the service.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane.executive_service import (
    CONTROL_PROTOCOL_VERSION,
    ExecutiveControlService,
    ServiceConfig,
    send_control_request,
)


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "ops" / "executive_os" / "acceptance.py"
SPEC = importlib.util.spec_from_file_location("executive_acceptance", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
acceptance = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = acceptance
SPEC.loader.exec_module(acceptance)


# A ``secrets.token_hex(32)`` value: the exact shape this runtime mints for the
# control environment canary and for its sentinel fixtures.
SECRET_HEX = "9f" * 32
# A ``secrets.token_urlsafe(32)`` value: the shape used for lease tokens.
SECRET_URLSAFE = "Ab-_" * 11


def _completed(
    *,
    returncode: int,
    stdout: bytes = b"",
    stderr: bytes = b"",
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(
        args=["executive_os_phase1c", "create-proof-job"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _envelope(code: str, message: str) -> bytes:
    """Render the CLI's stdout exactly as ``json.dumps(..., indent=2)`` does."""

    return (
        json.dumps(
            {"ok": False, "error": {"code": code, "message": message}},
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def _acceptance_stub(tmp_path: Path):
    """An ``Acceptance`` bound only to what ``_control_request`` reads.

    ``Acceptance.__init__`` resolves the four dedicated host principals through
    ``pwd``/``grp``; those accounts exist only on the reviewed Mac Studio, so the
    hermetic tests bind the handful of attributes the control path touches.
    """

    instance = object.__new__(acceptance.Acceptance)
    instance.operator_user = "operator"
    instance.operator_identity = SimpleNamespace(pw_dir=str(tmp_path))
    instance.python = Path(sys.executable)
    instance.release = tmp_path
    return instance


def _stub_subprocess(monkeypatch: pytest.MonkeyPatch, completed) -> list[dict]:
    """Replace only the acceptance module's ``subprocess`` reference.

    The real ``_run`` still executes, so its ``check`` handling stays under test:
    restoring ``check=True`` in ``_control_request`` makes ``_run`` raise the bare
    exit-code message and the refusal assertions fail.
    """

    calls: list[dict] = []

    def fake_run(argv, **kwargs):
        calls.append({"argv": list(argv), **kwargs})
        return completed

    monkeypatch.setattr(
        acceptance,
        "subprocess",
        types.SimpleNamespace(
            run=fake_run,
            DEVNULL=subprocess.DEVNULL,
            PIPE=subprocess.PIPE,
        ),
    )
    return calls


# ---------------------------------------------------------------------------
# 1. The structured envelope names the refusal
# ---------------------------------------------------------------------------


def test_refusal_detail_renders_the_structured_service_envelope():
    completed = _completed(
        returncode=2,
        stdout=_envelope(
            "request_failed",
            "workspace preparation failed: workspace command failed (128)",
        ),
    )
    detail = acceptance._refusal_detail(completed)
    assert detail == (
        "[request_failed] workspace preparation failed: "
        "workspace command failed (128)"
    )


def test_control_request_failure_names_the_exit_code_and_the_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    completed = _completed(
        returncode=2,
        stdout=_envelope(
            "request_failed",
            "workspace preparation failed: workspace command failed (128)",
        ),
    )
    _stub_subprocess(monkeypatch, completed)
    instance = _acceptance_stub(tmp_path)

    with pytest.raises(acceptance.AcceptanceError) as raised:
        instance._control_request("create-proof-job")

    message = str(raised.value)
    assert message == (
        "control command create-proof-job failed with exit 2: "
        "[request_failed] workspace preparation failed: "
        "workspace command failed (128)"
    )


# ---------------------------------------------------------------------------
# 2. Sanitization
# ---------------------------------------------------------------------------


def test_refusal_detail_collapses_newlines_and_strips_control_characters():
    completed = _completed(
        returncode=2,
        stdout=_envelope(
            "request_failed",
            "workspace command failed (128):\nfatal: refusing\r\n\tto clone\x00\x07 here",
        ),
    )
    detail = acceptance._refusal_detail(completed)
    assert detail is not None
    assert "\n" not in detail and "\r" not in detail and "\t" not in detail
    assert "\x00" not in detail and "\x07" not in detail
    assert detail == (
        "[request_failed] workspace command failed (128): "
        "fatal: refusing to clone here"
    )


def test_the_operator_visible_bound_and_markers_are_pinned():
    """Literals, not the constants under test.

    Asserting a constant against itself makes loosening the operator-visible
    bound (or emptying the truncation marker) invisible to this suite.
    """

    assert acceptance._REFUSAL_DETAIL_LIMIT == 300
    assert acceptance._REFUSAL_TRUNCATION_MARKER == "...[truncated]"
    assert acceptance._REFUSAL_REDACTION == "<redacted>"


def test_refusal_detail_truncates_an_overlong_message_with_a_marker():
    completed = _completed(
        returncode=2,
        stdout=_envelope("request_failed", "detail " * 400),
    )
    detail = acceptance._refusal_detail(completed)
    assert detail is not None
    assert detail.endswith("...[truncated]")
    assert len(detail) == 300 + len("...[truncated]")


def test_redaction_completes_before_the_length_bound():
    """Redact-before-bound is the whole safety argument; pin the ORDER.

    Truncating first can cut a secret-shaped run below the 32-character match
    threshold, and the surviving prefix is then printed verbatim.  The filler
    length is chosen so the boundary lands inside the first secret: 273 filler
    characters leave 27 characters of it above a 300-character cut, which is
    under the threshold and would therefore escape redaction entirely.
    """

    filler = "detail " * 39  # 273 chars, no run of 32+ token characters
    assert len(filler) == 273
    first = "9f" * 32  # 64 hex
    second = "ab" * 32  # 64 hex
    leaked_prefix = first[: 300 - len(filler)]
    assert len(leaked_prefix) == 27 < 32

    detail = acceptance._sanitize_refusal_fragment(f"{filler}{first} {second}")

    # Correct order: both secrets collapse to markers well inside the bound.
    assert first not in detail and second not in detail
    assert leaked_prefix not in detail
    assert detail.count("<redacted>") == 2
    assert not detail.endswith("...[truncated]")
    assert len(detail) <= 300


def test_refusal_detail_redacts_secret_shaped_material():
    completed = _completed(
        returncode=2,
        stdout=_envelope(
            "request_failed",
            f"canary mismatch {SECRET_HEX} against lease {SECRET_URLSAFE} at uid 450",
        ),
    )
    detail = acceptance._refusal_detail(completed)
    assert detail is not None
    assert SECRET_HEX not in detail
    assert SECRET_URLSAFE not in detail
    assert detail.count(acceptance._REFUSAL_REDACTION) == 2
    # Redaction must not eat the diagnostic around it.
    assert detail == (
        "[request_failed] canary mismatch <redacted> against lease "
        "<redacted> at uid 450"
    )


def test_a_git_object_id_survives_redaction_readable():
    """Exact-SHA comparison is this harness's proof premise.

    Redacting Git object ids would blind the operator to the one comparison the
    acceptance run exists to make.
    """

    expected = "1c94b3aa36e80ca7992ffef47dd8e4f87cb0959c"
    observed = "deadbeef" * 5
    assert len(expected) == len(observed) == 40
    completed = _completed(
        returncode=2,
        stdout=_envelope(
            "request_failed",
            f"expected base sha {expected} got {observed}",
        ),
    )
    assert acceptance._refusal_detail(completed) == (
        f"[request_failed] expected base sha {expected} got {observed}"
    )


def test_the_git_object_id_exemption_does_not_widen_to_real_secrets():
    """The exemption is exactly 40 lowercase hex, and nothing longer or shorter.

    Every secret this runtime mints is a different length: uuid4().hex is 32,
    secrets.token_urlsafe(32) is 43, secrets.token_hex(32) is 64.
    """

    sha = "1c94b3aa36e80ca7992ffef47dd8e4f87cb0959c"
    token = "9f" * 32  # secrets.token_hex(32) shape, 64 hex
    nonce = "3f" * 16  # uuid4().hex shape, 32 hex
    assert len(token) == 64 and len(nonce) == 32
    completed = _completed(
        returncode=2,
        stdout=_envelope(
            "request_failed",
            f"release {sha} rejected canary {token} nonce {nonce}",
        ),
    )
    detail = acceptance._refusal_detail(completed)
    assert detail == (
        f"[request_failed] release {sha} rejected canary <redacted> nonce <redacted>"
    )
    assert token not in detail
    assert nonce not in detail


def test_refusal_detail_redacts_an_exact_secret_the_run_holds():
    # Deliberately NOT token-shaped, so only the exact-match pass can catch it.
    held = "canary phrase with spaces"
    completed = _completed(
        returncode=2,
        stdout=_envelope("request_failed", f"probe saw {held} in the environment"),
    )
    assert held in str(acceptance._refusal_detail(completed))
    detail = acceptance._refusal_detail(completed, secrets_to_redact=(held,))
    assert detail is not None
    assert held not in detail
    assert detail == "[request_failed] probe saw <redacted> in the environment"


def test_control_request_redacts_a_plaintext_secret_the_run_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    held = "canary phrase with spaces"
    completed = _completed(
        returncode=2,
        stdout=_envelope("request_failed", f"probe saw {held} in the environment"),
    )
    _stub_subprocess(monkeypatch, completed)

    leaking = _acceptance_stub(tmp_path)
    with pytest.raises(acceptance.AcceptanceError) as raised:
        leaking._control_request("status")
    # Not token-shaped, so only `_refusal_redactions` can remove it.
    assert held in str(raised.value)

    holding = _acceptance_stub(tmp_path)
    holding.canary_value = held
    with pytest.raises(acceptance.AcceptanceError) as raised:
        holding._control_request("status")
    assert held not in str(raised.value)
    assert acceptance._REFUSAL_REDACTION in str(raised.value)


def test_control_request_redacts_a_secret_shaped_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    completed = _completed(
        returncode=2,
        stdout=_envelope("request_failed", f"attempt lease {SECRET_HEX} is not current"),
    )
    _stub_subprocess(monkeypatch, completed)
    instance = _acceptance_stub(tmp_path)

    with pytest.raises(acceptance.AcceptanceError) as raised:
        instance._control_request("dispatch", "job-1")

    message = str(raised.value)
    assert SECRET_HEX not in message
    assert acceptance._REFUSAL_REDACTION in message
    assert message.startswith("control command dispatch failed with exit 2:")


# ---------------------------------------------------------------------------
# 3. Fallback, and never inventing a reason
# ---------------------------------------------------------------------------


def test_refusal_detail_falls_back_to_a_bounded_stderr_excerpt():
    completed = _completed(
        returncode=2,
        stdout=b"",
        stderr=b"error: control socket path must be absolute\n",
    )
    detail = acceptance._refusal_detail(completed)
    assert detail == "error: control socket path must be absolute"


def test_refusal_detail_bounds_and_sanitizes_the_stderr_fallback():
    completed = _completed(
        returncode=2,
        stdout=b"not json at all",
        stderr=("error: " + SECRET_HEX + " ").encode("utf-8") + b"boom\n" * 400,
    )
    detail = acceptance._refusal_detail(completed)
    assert detail is not None
    assert SECRET_HEX not in detail
    assert "\n" not in detail
    assert detail.endswith(acceptance._REFUSAL_TRUNCATION_MARKER)


def test_refusal_detail_invents_nothing_for_non_envelope_json():
    completed = _completed(
        returncode=2,
        stdout=b'{"ok": true, "result": {"job_id": "job-1"}}\n',
        stderr=b"",
    )
    assert acceptance._refusal_detail(completed) is None


def test_control_request_names_the_exit_code_when_no_reason_is_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    completed = _completed(returncode=2, stdout=b"{}\n", stderr=b"   \n")
    _stub_subprocess(monkeypatch, completed)
    instance = _acceptance_stub(tmp_path)

    with pytest.raises(acceptance.AcceptanceError) as raised:
        instance._control_request("create-proof-job")

    assert str(raised.value) == (
        "control command create-proof-job failed with exit 2 "
        "(no structured refusal reason available)"
    )


# ---------------------------------------------------------------------------
# 4. Fail-closed behavior is unchanged
# ---------------------------------------------------------------------------


def test_successful_control_request_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    payload = {"ok": True, "result": {"job_id": "job-1", "worktree": "/tmp/proof-1"}}
    completed = _completed(
        returncode=0,
        stdout=(json.dumps(payload) + "\n").encode("utf-8"),
    )
    _stub_subprocess(monkeypatch, completed)
    instance = _acceptance_stub(tmp_path)

    assert instance._control_request("create-proof-job") == payload


def test_rejected_envelope_on_a_zero_exit_still_raises_was_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    completed = _completed(
        returncode=0,
        stdout=_envelope("peer_denied", "peer uid is not authorized"),
    )
    _stub_subprocess(monkeypatch, completed)
    instance = _acceptance_stub(tmp_path)

    with pytest.raises(acceptance.AcceptanceError) as raised:
        instance._control_request("create-proof-job")

    assert str(raised.value) == "control command create-proof-job was rejected"


# ---------------------------------------------------------------------------
# 5. `_run` is unchanged for every other acceptance command
# ---------------------------------------------------------------------------


def test_run_does_not_dump_stderr_for_non_control_commands():
    with pytest.raises(acceptance.AcceptanceError) as raised:
        acceptance._run(
            ["/bin/sh", "-c", "echo STDERR-MUST-NOT-LEAK >&2; exit 3"],
            label="worker broker status",
        )

    message = str(raised.value)
    assert message == "worker broker status failed with exit 3"
    assert "STDERR-MUST-NOT-LEAK" not in message


def test_run_still_returns_the_completed_process_when_check_is_disabled():
    completed = acceptance._run(
        ["/bin/sh", "-c", "echo out; echo err >&2; exit 4"],
        label="worker broker status",
        check=False,
    )
    assert completed.returncode == 4
    assert completed.stdout == b"out\n"
    assert completed.stderr == b"err\n"


# ---------------------------------------------------------------------------
# 6. A client that disconnects during error delivery
# ---------------------------------------------------------------------------


class _FixedReader:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    async def readuntil(self, separator: bytes = b"\n") -> bytes:
        return self._payload


class _DisconnectingWriter:
    """A writer that fails at exactly one delivery/teardown point."""

    def __init__(self, connection: socket.socket, *, fail_on: str, error: type) -> None:
        self._connection = connection
        self._fail_on = fail_on
        self._error = error
        self.closed = False

    def _maybe_fail(self, point: str) -> None:
        if self._fail_on == point:
            raise self._error("peer closed the control connection")

    def get_extra_info(self, name: str, default=None):
        return self._connection if name == "socket" else default

    def write(self, raw: bytes) -> None:
        self._maybe_fail("write")

    async def drain(self) -> None:
        self._maybe_fail("drain")

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        self._maybe_fail("wait_closed")


def _control_line(command: str = "status") -> bytes:
    return (
        json.dumps(
            {"version": CONTROL_PROTOCOL_VERSION, "command": command, "args": {}},
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _offline_config(tmp_path: Path, socket_root: Path) -> ServiceConfig:
    return ServiceConfig(
        runtime_root=tmp_path / "runtime",
        socket_path=socket_root / "executive.sock",
        proof_source_repository=tmp_path / "source",
        proof_workspace_root=tmp_path / "workspaces",
        proof_base_sha="a" * 40,
        shutdown_grace_seconds=0.1,
    )


@pytest.fixture
def short_socket_root():
    # Darwin's sockaddr_un path ceiling is 104 bytes; pytest's tmp_path is longer
    # than a production /var/run path.
    value = Path(tempfile.mkdtemp(prefix="mmx-obs-", dir="/tmp"))
    try:
        yield value
    finally:
        shutil.rmtree(value, ignore_errors=True)


def _drive_handler(service, writer) -> None:
    asyncio.run(service._handle_connection(_FixedReader(_control_line()), writer))


@pytest.mark.parametrize("fail_on", ["write", "drain", "wait_closed"])
@pytest.mark.parametrize(
    "error", [ConnectionResetError, BrokenPipeError, ConnectionAbortedError]
)
def test_client_disconnect_during_error_delivery_does_not_propagate(
    tmp_path: Path, short_socket_root: Path, fail_on: str, error: type
):
    # An unstarted service refuses every command with `request_failed`, which is
    # precisely the error-envelope delivery the vanished client aborts.
    service = ExecutiveControlService(_offline_config(tmp_path, short_socket_root))
    local, peer = socket.socketpair()
    writer = _DisconnectingWriter(local, fail_on=fail_on, error=error)
    try:
        _drive_handler(service, writer)
    finally:
        local.close()
        peer.close()
    assert writer.closed is True


@pytest.mark.parametrize("fail_on", ["write", "drain", "wait_closed"])
@pytest.mark.parametrize("error", [RuntimeError, ValueError])
def test_a_non_connection_error_during_delivery_still_propagates(
    tmp_path: Path, short_socket_root: Path, fail_on: str, error: type
):
    """The swallow is narrow by design; pin it against WIDENING.

    Nothing in the code stops a future `except Exception` here, which would turn
    the delivery path into a sink for every server-side fault.  A non-connection
    error must still reach the caller.
    """

    service = ExecutiveControlService(_offline_config(tmp_path, short_socket_root))
    local, peer = socket.socketpair()
    writer = _DisconnectingWriter(local, fail_on=fail_on, error=error)
    try:
        with pytest.raises(error):
            _drive_handler(service, writer)
    finally:
        local.close()
        peer.close()


def test_error_delivery_reaches_a_healthy_client_unchanged(
    tmp_path: Path, short_socket_root: Path
):
    """The hardening must not swallow a reply a live client can still receive."""

    delivered: list[bytes] = []

    class _HealthyWriter(_DisconnectingWriter):
        def write(self, raw: bytes) -> None:
            delivered.append(raw)

        async def drain(self) -> None:
            return None

    service = ExecutiveControlService(_offline_config(tmp_path, short_socket_root))
    local, peer = socket.socketpair()
    writer = _HealthyWriter(local, fail_on="never", error=ConnectionResetError)
    try:
        asyncio.run(
            service._handle_connection(_FixedReader(_control_line()), writer)
        )
    finally:
        local.close()
        peer.close()

    assert len(delivered) == 1
    envelope = json.loads(delivered[0])
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "request_failed"


class _StubSupervisor:
    def __init__(self, runtime) -> None:
        self.runtime = runtime

    def reconcile_restart(self, *, requeue_lost: bool = False):
        return []


def test_service_still_serves_after_an_abrupt_client_disconnect(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise():
        service = ExecutiveControlService(
            _offline_config(tmp_path, short_socket_root),
            supervisor_factory=_StubSupervisor,
        )
        unhandled: list[dict] = []
        asyncio.get_running_loop().set_exception_handler(
            lambda loop, context: unhandled.append(context)
        )
        await service.start()
        try:
            assert (await send_control_request(service.socket_path, "status"))["ok"] is True

            # Send a request, then abort the connection with an RST before
            # reading anything back.
            aborting = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            aborting.connect(str(service.socket_path))
            aborting.sendall(_control_line())
            aborting.setsockopt(
                socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0)
            )
            aborting.close()
            await asyncio.sleep(0.2)

            after = await send_control_request(service.socket_path, "status")
            assert after["ok"] is True
            assert after["result"]["protocol"] == CONTROL_PROTOCOL_VERSION
        finally:
            await service.close()
        assert unhandled == []

    asyncio.run(exercise())
