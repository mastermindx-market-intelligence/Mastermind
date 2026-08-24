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
import os
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
# 5b. `_broker_status` names WHY the broker refused to answer
#
# Phase 1C acceptance failed at `worker broker status failed with exit 1` with
# no reason attached: the probe runs a `python -c` snippet, so a broker that
# refuses to start raises there and the traceback goes to STDERR -- which
# `_run(check=True)` discarded.  The stderr fallback is the load-bearing path
# for this probe; there is no structured envelope to prefer.
# ---------------------------------------------------------------------------


def _broker_status_stub(tmp_path: Path):
    """An ``Acceptance`` bound only to what ``_broker_status`` reads."""

    instance = _acceptance_stub(tmp_path)
    instance.control_identity = SimpleNamespace(pw_dir=str(tmp_path))
    instance.worker_identity = SimpleNamespace(pw_uid=451)
    instance.worker_group = SimpleNamespace(gr_gid=451)
    instance.worker_config = {
        "allowed_supplementary_gids": [],
        "operator_harness_armed": False,
    }
    # The real `_write_bytes` chowns to the dedicated control principal, which
    # exists only on the reviewed host; receipt persistence is not under test.
    instance.persisted = {}
    instance._write_json = instance.persisted.__setitem__
    return instance


_STARTUP_SWEEP_TRACEBACK = (
    b'Traceback (most recent call last):\n'
    b'  File "<string>", line 1, in <module>\n'
    b"control_plane.executive_worker_broker.DedicatedUIDError: "
    b"worker UID did not become quiescent after SIGKILL\n"
)


def test_broker_status_failure_names_the_stderr_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    completed = _completed(returncode=1, stderr=_STARTUP_SWEEP_TRACEBACK)
    _stub_subprocess(monkeypatch, completed)
    instance = _broker_status_stub(tmp_path)

    with pytest.raises(acceptance.AcceptanceError) as raised:
        instance._broker_status("worker-broker-startup.json")

    message = str(raised.value)
    prefix = "worker broker status failed with exit 1: "
    assert message.startswith(prefix)
    # The actual cause, not a bare exit code.
    assert "worker UID did not become quiescent after SIGKILL" in message
    # Bounded and single-line: the sanitizer collapsed the traceback.
    assert "\n" not in message
    assert len(message) - len(prefix) <= acceptance._REFUSAL_DETAIL_LIMIT + len(
        acceptance._REFUSAL_TRUNCATION_MARKER
    )


def test_broker_status_failure_bounds_an_enormous_stderr_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A runaway traceback must be truncated, not pasted into the error.

    Deliberately built from short words, so the length bound is what truncates
    it -- a long unbroken run would be redacted as secret-shaped first and
    would prove the wrong rule.
    """

    completed = _completed(
        returncode=1,
        stderr=b'  File "<string>", line 1, in <module>\n' * 2_000,
    )
    _stub_subprocess(monkeypatch, completed)
    instance = _broker_status_stub(tmp_path)

    with pytest.raises(acceptance.AcceptanceError) as raised:
        instance._broker_status("worker-broker-startup.json")

    message = str(raised.value)
    prefix = "worker broker status failed with exit 1: "
    assert message.endswith(acceptance._REFUSAL_TRUNCATION_MARKER)
    assert len(message) - len(prefix) == acceptance._REFUSAL_DETAIL_LIMIT + len(
        acceptance._REFUSAL_TRUNCATION_MARKER
    )


def test_broker_status_failure_redacts_a_secret_shaped_stderr_fragment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The probe's stderr is external text: it goes through the SAME sanitizer."""

    completed = _completed(
        returncode=1,
        stderr=f"RuntimeError: refused for token {SECRET_HEX}\n".encode("utf-8"),
    )
    _stub_subprocess(monkeypatch, completed)
    instance = _broker_status_stub(tmp_path)

    with pytest.raises(acceptance.AcceptanceError) as raised:
        instance._broker_status("worker-broker-startup.json")

    message = str(raised.value)
    assert SECRET_HEX not in message
    assert acceptance._REFUSAL_REDACTION in message


def test_broker_status_failure_without_any_reason_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Never invent a cause: silence is reported as silence, not as a guess."""

    _stub_subprocess(monkeypatch, _completed(returncode=1))
    instance = _broker_status_stub(tmp_path)

    with pytest.raises(acceptance.AcceptanceError) as raised:
        instance._broker_status("worker-broker-startup.json")

    assert str(raised.value) == (
        "worker broker status failed with exit 1 (no structured refusal reason available)"
    )


def test_broker_status_success_path_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A zero exit still parses, still attests, and still persists the receipt."""

    value = {
        "worker_uid": 451,
        "worker_gid": 451,
        "supplementary_gids": [],
        "operator_harness_armed": False,
        "active_operator_attempt_id": None,
        "active_operator_generation_id": None,
        "startup_sweep": {"passed": True},
        "quarantined_reason": None,
    }
    completed = _completed(
        returncode=0,
        stdout=(json.dumps(value) + "\n").encode("utf-8"),
    )
    _stub_subprocess(monkeypatch, completed)
    instance = _broker_status_stub(tmp_path)

    assert instance._broker_status("worker-broker-startup.json") == value
    assert instance.persisted == {"worker-broker-startup.json": value}


def test_broker_status_still_refuses_a_zero_exit_that_fails_attestation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The exit-code path must not become the only gate on the attestation."""

    value = {
        "worker_uid": 451,
        "worker_gid": 451,
        "supplementary_gids": [],
        "operator_harness_armed": False,
        "active_operator_attempt_id": None,
        "active_operator_generation_id": None,
        "startup_sweep": {"passed": False},
        "quarantined_reason": None,
    }
    _stub_subprocess(
        monkeypatch,
        _completed(returncode=0, stdout=(json.dumps(value) + "\n").encode("utf-8")),
    )
    instance = _broker_status_stub(tmp_path)

    with pytest.raises(acceptance.AcceptanceError) as raised:
        instance._broker_status("worker-broker-startup.json")

    assert str(raised.value) == (
        "worker broker did not attest the dedicated principal boundary"
    )


def test_broker_status_refuses_operator_arm_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = {
        "worker_uid": 451,
        "worker_gid": 451,
        "supplementary_gids": [],
        "operator_harness_armed": True,
        "active_operator_attempt_id": None,
        "active_operator_generation_id": None,
        "startup_sweep": {"passed": True},
        "quarantined_reason": None,
    }
    _stub_subprocess(
        monkeypatch,
        _completed(returncode=0, stdout=(json.dumps(value) + "\n").encode("utf-8")),
    )
    instance = _broker_status_stub(tmp_path)

    with pytest.raises(acceptance.AcceptanceError, match="principal boundary"):
        instance._broker_status("worker-broker-startup.json")


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


def test_wait_job_records_quarantine_status_and_dispatch_errors(
    tmp_path: Path,
) -> None:
    instance = _acceptance_stub(tmp_path)
    instance.persisted = {}
    instance._write_json = instance.persisted.__setitem__
    instance.helper_pid = None
    instance.services_started = True
    instance.release = tmp_path
    instance._pid_exists = lambda _pid: False

    def fake_control(command, *values, persist=None):
        if command == "job":
            raise acceptance.AcceptanceError(
                "control command job failed with exit 2: "
                "[state_conflict] Executive control service is QUARANTINED; "
                "only status, health, and canary activation are available"
            )
        if command == "status":
            return {
                "ok": True,
                "result": {
                    "service_state": "QUARANTINED",
                    "dispatch_errors": {
                        "JOB-001": (
                            "BrokerStateError: worker left a detached "
                            "same-UID process after collection"
                        )
                    },
                },
            }
        raise AssertionError(command)

    instance._control_request = fake_control
    instance._broker_status = lambda persist: instance.persisted.__setitem__(
        persist,
        {"last_sweep": {"reason": "run_terminal", "ambient_pids": [88688]}},
    ) or {"last_sweep": {"reason": "run_terminal", "ambient_pids": [88688]}}

    with pytest.raises(acceptance.AcceptanceError, match="QUARANTINED"):
        instance._wait_job("JOB-001", {"COMPLETED"}, timeout=1.0)

    quarantine = instance.persisted["quarantine-status.json"]["result"]
    assert quarantine["service_state"] == "QUARANTINED"
    assert "JOB-001" in quarantine["dispatch_errors"]
    assert "detached" in quarantine["dispatch_errors"]["JOB-001"]
    assert instance.persisted["quarantine-worker-broker.json"]["last_sweep"]["reason"] == (
        "run_terminal"
    )


def test_cleanup_after_failure_captures_status_before_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = _acceptance_stub(tmp_path)
    instance.persisted = {}
    instance._write_json = instance.persisted.__setitem__
    instance.helper_pid = None
    instance.services_started = True
    instance.release = tmp_path
    instance._pid_exists = lambda _pid: False
    stopped: list[str] = []

    def fake_control(command, *values, persist=None):
        assert command == "status"
        return {
            "ok": True,
            "result": {
                "service_state": "QUARANTINED",
                "dispatch_errors": {"JOB-001": "BrokerStateError: fixture"},
            },
        }

    instance._control_request = fake_control
    instance._broker_status = lambda persist: {"last_sweep": {"reason": "run_terminal"}}

    def fake_run(argv, **kwargs):
        stopped.append(str(argv[-1]) if argv else "")
        return _completed(returncode=0)

    monkeypatch.setattr(
        acceptance,
        "subprocess",
        types.SimpleNamespace(
            run=fake_run,
            DEVNULL=subprocess.DEVNULL,
            PIPE=subprocess.PIPE,
        ),
    )
    (tmp_path / "ops" / "executive_os").mkdir(parents=True)
    (tmp_path / "ops" / "executive_os" / "service-control.sh").write_text(
        "#!/bin/sh\n", encoding="utf-8"
    )
    instance.cleanup_after_failure()
    assert instance.persisted["quarantine-status.json"]["result"]["service_state"] == (
        "QUARANTINED"
    )
    assert "stop" in stopped[-1]


PREFLIGHT_PATH = ROOT / "ops" / "executive_os" / "git_handoff_preflight.py"
PREFLIGHT_SPEC = importlib.util.spec_from_file_location(
    "executive_git_handoff_preflight", PREFLIGHT_PATH
)
assert PREFLIGHT_SPEC is not None and PREFLIGHT_SPEC.loader is not None
preflight = importlib.util.module_from_spec(PREFLIGHT_SPEC)
sys.modules[PREFLIGHT_SPEC.name] = preflight
PREFLIGHT_SPEC.loader.exec_module(preflight)


def test_gate_b_receipt_validation_and_failure_formatting():
    sha = "a" * 40
    receipt = {
        "schema_version": preflight.SCHEMA_VERSION,
        "passed": True,
        "observed_at": "2026-08-16T00:00:00+00:00",
        "release_sha": sha,
        "control": {"uid": 450, "gid": 450},
        "worker": {"uid": 451, "gid": 451},
        "workspace": {"path": "gate-b-deadbeefcafe", "uid": 450, "gid": 451, "mode": 0o750},
        "index_before_service_observation": {"inode": 1, "mode": 0o640},
        "index_after_service_observation": {"inode": 1, "mode": 0o640},
        "index_after_worker_preflight": {"inode": 1, "mode": 0o640},
        "git": {
            "head": sha,
            "branch": "codex/gate-b-deadbeefcafe",
            "remote_count": 0,
            "status_dirty": False,
            "all_untracked_dirty": False,
            "launch_clean": True,
        },
        "persistent_config_unchanged": True,
        "worker_preflight_passed": True,
        "workspace_root_restored": True,
        "stimulus_used": preflight.STIMULUS_METHOD,
        "stimulus": {
            "path": "README.md",
            "selection_method": preflight.STIMULUS_METHOD,
            "bytes_unchanged": True,
            "size_unchanged": True,
            "ownership_mode_unchanged": True,
        },
    }
    preflight.validate_receipt(receipt)
    failed = preflight.failure_receipt(release_sha=sha, reason="x" * 500)
    assert failed["passed"] is False
    assert failed["schema_version"] == preflight.SCHEMA_VERSION
    assert len(failed["error"]) <= 300 + len("...[truncated]")
    with pytest.raises(preflight.PreflightError, match="missing"):
        preflight.validate_receipt({"schema_version": preflight.SCHEMA_VERSION, "passed": True})


def test_gate_b_requires_darwin_root(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(preflight.sys, "platform", "linux")
    monkeypatch.setattr(preflight.os, "geteuid", lambda: 0)
    with pytest.raises(preflight.PreflightError, match="darwin"):
        preflight.require_darwin_root()
    monkeypatch.setattr(preflight.sys, "platform", "darwin")
    monkeypatch.setattr(preflight.os, "geteuid", lambda: 501)
    with pytest.raises(preflight.PreflightError, match="euid 0"):
        preflight.require_darwin_root()


def test_gate_b_refuses_identity_mismatch(monkeypatch: pytest.MonkeyPatch):
    control = types.SimpleNamespace(pw_uid=450, pw_gid=450, pw_dir="/var/empty")
    worker = types.SimpleNamespace(pw_uid=450, pw_gid=451, pw_dir="/var/empty")

    def fake_pwnam(name: str):
        return control if name.endswith("exec") else worker

    monkeypatch.setattr(preflight.pwd, "getpwnam", fake_pwnam)
    monkeypatch.setattr(preflight.grp, "getgrall", lambda: [])
    with pytest.raises(preflight.PreflightError, match="must differ"):
        preflight.require_distinct_identities(
            control_user="_mastermind_exec", worker_user="_mastermind_worker"
        )


def test_gate_b_refuses_unsafe_workspace_root_and_probe_id(tmp_path: Path):
    world = tmp_path / "world"
    world.mkdir()
    world.chmod(0o755)
    with pytest.raises(preflight.PreflightError, match="unsafe workspace-root"):
        preflight.require_workspace_root_metadata(world, control_uid=os.geteuid())
    with pytest.raises(preflight.PreflightError, match="unsafe generated probe id"):
        preflight.require_probe_id("../escape")
    with pytest.raises(preflight.PreflightError, match="unsafe generated probe id"):
        preflight.require_probe_id("gate-b-*")
    assert preflight.require_probe_id("gate-b-deadbeefcafe") == "gate-b-deadbeefcafe"


def test_gate_b_cleanup_plan_and_root_restore(tmp_path: Path):
    root = tmp_path / "workspaces"
    root.mkdir(mode=0o700)
    home = root / ".supervisor-home"
    home.mkdir(mode=0o700)
    before = preflight.snapshot_workspace_root(root)
    plan = preflight.cleanup_plan(
        workspace=root / "gate-b-deadbeefcafe",
        workspace_root=root,
        supervisor_home_existed=True,
        supervisor_home=home,
    )
    assert plan["remove_workspace"] is True
    assert plan["touch_supervisor_home"] is False
    (root / "probe-corpse").mkdir()
    after = preflight.snapshot_workspace_root(root)
    assert preflight.workspace_root_restored(before, after) is False
    (root / "probe-corpse").rmdir()
    assert preflight.workspace_root_restored(before, preflight.snapshot_workspace_root(root))


def test_gate_b_index_and_persistent_config_comparison(tmp_path: Path):
    index = tmp_path / "index"
    index.write_bytes(b"idx")
    index.chmod(0o640)
    meta = preflight.index_metadata(index)
    assert preflight.index_handoff_ok(
        meta, control_uid=os.geteuid(), shared_gid=os.getegid()
    )
    assert preflight.index_observation_stable(meta, dict(meta))
    changed = dict(meta)
    changed["mode"] = 0o600
    assert preflight.index_handoff_ok(
        changed, control_uid=os.geteuid(), shared_gid=os.getegid()
    ) is False
    assert preflight.index_observation_stable(meta, changed) is False
    config = tmp_path / "config"
    config.write_text("[core]\n", encoding="utf-8")
    config.chmod(0o640)
    identity = preflight.config_identity(config)
    assert preflight.persistent_config_unchanged(identity, dict(identity))
    mutated = dict(identity)
    mutated["sha256"] = "0" * 64
    assert preflight.persistent_config_unchanged(identity, mutated) is False


def test_gate_b_worker_receipt_validation():
    sha = "b" * 40
    preflight.validate_worker_preflight_receipt(
        {
            "passed": True,
            "head": sha,
            "remote_count": 0,
            "launch_clean": True,
            "persistent_trust_changed": False,
        },
        expected_sha=sha,
    )
    with pytest.raises(preflight.PreflightError, match="HEAD"):
        preflight.validate_worker_preflight_receipt(
            {
                "passed": True,
                "head": "c" * 40,
                "remote_count": 0,
                "launch_clean": True,
                "persistent_trust_changed": False,
            },
            expected_sha=sha,
        )
