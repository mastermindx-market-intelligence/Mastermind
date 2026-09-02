"""C0 falsifier — bounded stdio JSON-RPC client.

Every test here is a way a language server can misbehave or be substituted.
The client must fail closed and typed, never hang, never fall back to a shell,
and never carry the host environment into the child.
"""

from __future__ import annotations

import functools
import hashlib
import sys
from pathlib import Path

import pytest

from experiments.code_intelligence.backend import ExecutableSpec
from experiments.code_intelligence.jsonrpc_stdio import (
    MAX_FRAME_BYTES,
    MAX_STDERR_BYTES,
    JsonRpcError,
    JsonRpcStdioClient,
)

SERVER = Path(__file__).parent / "servers" / "fake_jsonrpc_server.py"

# Injected by the platform into every child process, not by this client.
OS_INJECTED_ENV = {"__CF_USER_TEXT_ENCODING"}


# sys.executable is a symlink under Homebrew; the client refuses symlinked
# executables on purpose, so the harness pins the resolved real binary.
PYTHON = Path(sys.executable).resolve()


@functools.lru_cache(maxsize=1)
def _python_digest() -> str:
    return hashlib.sha256(PYTHON.read_bytes()).hexdigest()


def _spec(mode: str, sha256: str | None = None) -> ExecutableSpec:
    return ExecutableSpec(
        path=PYTHON,
        sha256=sha256 or _python_digest(),
        argv_suffix=(str(SERVER), mode),
    )


def _client(mode: str, tmp_path: Path, **kwargs) -> JsonRpcStdioClient:
    return JsonRpcStdioClient(spec=_spec(mode), scratch=tmp_path, **kwargs)


class TestDigestPinning:
    def test_wrong_digest_refuses_to_launch(self, tmp_path: Path) -> None:
        client = JsonRpcStdioClient(spec=_spec("echo", "0" * 64), scratch=tmp_path)
        with pytest.raises(JsonRpcError) as excinfo:
            client.start()
        assert excinfo.value.code == "EXECUTABLE_DIGEST_MISMATCH"

    def test_missing_executable_is_refused(self, tmp_path: Path) -> None:
        spec = ExecutableSpec(
            path=tmp_path / "nope", sha256="0" * 64, argv_suffix=()
        )
        client = JsonRpcStdioClient(spec=spec, scratch=tmp_path)
        with pytest.raises(JsonRpcError) as excinfo:
            client.start()
        assert excinfo.value.code == "EXECUTABLE_UNAVAILABLE"

    def test_symlinked_executable_is_refused(self, tmp_path: Path) -> None:
        link = tmp_path / "python-link"
        link.symlink_to(PYTHON)
        spec = ExecutableSpec(path=link, sha256=_python_digest(), argv_suffix=())
        client = JsonRpcStdioClient(spec=spec, scratch=tmp_path)
        with pytest.raises(JsonRpcError) as excinfo:
            client.start()
        assert excinfo.value.code == "EXECUTABLE_SYMLINK_REFUSED"

    def test_correct_digest_starts(self, tmp_path: Path) -> None:
        client = _client("echo", tmp_path)
        client.start()
        try:
            assert client.is_running
        finally:
            client.close()


class TestFraming:
    def test_simple_round_trip(self, tmp_path: Path) -> None:
        client = _client("echo", tmp_path)
        client.start()
        try:
            result = client.request("ping", {"a": 1})
            assert result == {"method": "ping", "params": {"a": 1}}
        finally:
            client.close()

    def test_split_headers_and_body_are_reassembled(self, tmp_path: Path) -> None:
        client = _client("split", tmp_path)
        client.start()
        try:
            assert client.request("ping", {}) == {"ok": True}
        finally:
            client.close()

    def test_two_messages_in_one_write_are_separated(self, tmp_path: Path) -> None:
        client = _client("batch2", tmp_path)
        client.start()
        try:
            assert client.request("ping", {}) == {"ok": True}
            assert any(
                note["method"] == "window/logMessage" for note in client.drain_notifications()
            )
        finally:
            client.close()

    def test_malformed_content_length_is_typed(self, tmp_path: Path) -> None:
        client = _client("badlen", tmp_path)
        client.start()
        with pytest.raises(JsonRpcError) as excinfo:
            client.request("ping", {}, timeout=5)
        assert excinfo.value.code == "PROTOCOL_MALFORMED_HEADER"
        client.close()

    def test_missing_content_length_is_typed(self, tmp_path: Path) -> None:
        client = _client("noheader", tmp_path)
        client.start()
        with pytest.raises(JsonRpcError) as excinfo:
            client.request("ping", {}, timeout=5)
        assert excinfo.value.code == "PROTOCOL_MALFORMED_HEADER"
        client.close()

    def test_oversized_frame_is_refused_before_reading_it(self, tmp_path: Path) -> None:
        client = _client("huge", tmp_path)
        client.start()
        with pytest.raises(JsonRpcError) as excinfo:
            client.request("ping", {}, timeout=5)
        assert excinfo.value.code == "PROTOCOL_FRAME_TOO_LARGE"
        client.close()

    def test_frame_ceiling_is_four_mib(self) -> None:
        assert MAX_FRAME_BYTES == 4 * 1024 * 1024


class TestNotifications:
    def test_notification_queue_is_bounded(self, tmp_path: Path) -> None:
        client = _client("notify", tmp_path, max_notifications=10)
        client.start()
        try:
            client.request("ping", {})
            assert len(client.drain_notifications()) <= 10
        finally:
            client.close()

    def test_unsolicited_notifications_do_not_break_requests(self, tmp_path: Path) -> None:
        client = _client("notify", tmp_path)
        client.start()
        try:
            assert client.request("ping", {}) == {"ok": True}
        finally:
            client.close()

    def test_notify_sends_without_expecting_a_reply(self, tmp_path: Path) -> None:
        client = _client("echo", tmp_path)
        client.start()
        try:
            client.notify("initialized", {})
            assert client.request("ping", {}) == {"method": "ping", "params": {}}
        finally:
            client.close()


class TestFailureModes:
    def test_timeout_is_typed_and_bounded(self, tmp_path: Path) -> None:
        client = _client("silent", tmp_path)
        client.start()
        with pytest.raises(JsonRpcError) as excinfo:
            client.request("ping", {}, timeout=1)
        assert excinfo.value.code == "REQUEST_TIMEOUT"
        client.close()

    def test_timeout_sends_a_cancel(self, tmp_path: Path) -> None:
        client = _client("silent_log", tmp_path)
        client.start()
        try:
            with pytest.raises(JsonRpcError):
                client.request("slow", {}, timeout=1)
            result = client.request("report", {}, timeout=10)
            assert result["cancelled"], "client must cancel a timed-out request"
        finally:
            client.close()

    def test_child_exit_is_typed(self, tmp_path: Path) -> None:
        client = _client("exit", tmp_path)
        client.start()
        with pytest.raises(JsonRpcError) as excinfo:
            client.request("ping", {}, timeout=5)
        assert excinfo.value.code == "SERVER_EXITED"
        client.close()

    def test_crash_after_reply_is_visible_on_the_next_call(self, tmp_path: Path) -> None:
        client = _client("crash_after", tmp_path)
        client.start()
        try:
            assert client.request("ping", {}, timeout=10) == {"ok": True}
            with pytest.raises(JsonRpcError) as excinfo:
                client.request("ping", {}, timeout=5)
            assert excinfo.value.code == "SERVER_EXITED"
        finally:
            client.close()

    def test_server_error_is_typed_not_raised_as_result(self, tmp_path: Path) -> None:
        client = _client("error", tmp_path)
        client.start()
        try:
            with pytest.raises(JsonRpcError) as excinfo:
                client.request("ping", {}, timeout=10)
            assert excinfo.value.code == "SERVER_ERROR"
        finally:
            client.close()

    def test_request_before_start_is_refused(self, tmp_path: Path) -> None:
        client = _client("echo", tmp_path)
        with pytest.raises(JsonRpcError) as excinfo:
            client.request("ping", {})
        assert excinfo.value.code == "SERVER_NOT_STARTED"

    def test_close_is_idempotent(self, tmp_path: Path) -> None:
        client = _client("echo", tmp_path)
        client.start()
        client.close()
        client.close()
        assert not client.is_running


class TestBoundedStderr:
    def test_stderr_is_retained_but_capped(self, tmp_path: Path) -> None:
        client = _client("stderr", tmp_path)
        client.start()
        try:
            client.request("ping", {}, timeout=20)
            captured = client.stderr_tail()
            assert len(captured) <= MAX_STDERR_BYTES
            assert b"E" in captured
        finally:
            client.close()

    def test_stderr_ceiling_is_thirty_two_kib(self) -> None:
        assert MAX_STDERR_BYTES == 32 * 1024


class TestClosedEnvironment:
    def test_child_environment_is_closed(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("MASTERMIND_C0_SECRET", "must-not-propagate")
        client = _client("env", tmp_path)
        client.start()
        try:
            keys = client.request("ping", {}, timeout=10)["env_keys"]
            assert "MASTERMIND_C0_SECRET" not in keys
            # macOS CoreFoundation injects __CF_USER_TEXT_ENCODING into every
            # spawned process. It is not passed by this client and cannot be
            # suppressed from here; it is recorded as a residual observation in
            # the C0 result rather than hidden by a looser assertion.
            assert set(keys) - set(client.child_env_allowlist) <= OS_INJECTED_ENV
        finally:
            client.close()

    def test_no_host_variable_leaks_into_the_child(self, tmp_path: Path, monkeypatch) -> None:
        for name in ("AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN", "OPENAI_API_KEY"):
            monkeypatch.setenv(name, "leaked")
        client = _client("env", tmp_path)
        client.start()
        try:
            keys = set(client.request("ping", {}, timeout=10)["env_keys"])
            assert not keys & {"AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN", "OPENAI_API_KEY"}
        finally:
            client.close()

    def test_no_shell_is_used(self, tmp_path: Path) -> None:
        client = _client("echo", tmp_path)
        client.start()
        try:
            assert client.launch_argv[0] == str(PYTHON)
            assert client.used_shell is False
        finally:
            client.close()


class TestB6Enforcement:
    """B6 — the transport must enforce, not merely declare, its boundary."""

    def _sandboxed(self, mode: str, tmp_path: Path) -> JsonRpcStdioClient:
        from experiments.code_intelligence.sandbox import build_sandbox

        return JsonRpcStdioClient(
            spec=_spec(mode),
            scratch=tmp_path,
            sandbox=build_sandbox(scratch=tmp_path / "sbx"),
        )

    def test_client_runs_the_child_under_the_sandbox(self, tmp_path: Path) -> None:
        client = self._sandboxed("echo", tmp_path)
        client.start()
        try:
            assert client.launch_argv[0].endswith("sandbox-exec")
            assert client.request("ping", {}) == {"method": "ping", "params": {}}
        finally:
            client.close()

    def test_oversized_header_is_refused(self, tmp_path: Path) -> None:
        client = _client("hugeheader", tmp_path)
        client.start()
        with pytest.raises(JsonRpcError) as excinfo:
            client.request("ping", {}, timeout=8)
        assert excinfo.value.code == "PROTOCOL_HEADER_TOO_LARGE"
        client.close()

    def test_server_initiated_mutation_request_is_a_hard_failure(
        self, tmp_path: Path
    ) -> None:
        client = _client("mutate", tmp_path)
        client.start()
        try:
            with pytest.raises(JsonRpcError) as excinfo:
                client.request("ping", {}, timeout=10)
            assert excinfo.value.code == "SERVER_INITIATED_MUTATION_REFUSED"
            assert "workspace/applyEdit" in excinfo.value.detail
        finally:
            client.close()

    def test_close_receipts_the_process_group(self, tmp_path: Path) -> None:
        client = _client("echo", tmp_path)
        client.start()
        client.request("ping", {})
        client.close()
        receipt = client.shutdown_receipt()
        assert receipt["group_signalled"] in (True, False)
        assert receipt["descendants_alive"] == 0, receipt

    def test_descendants_are_killed_with_the_group(self, tmp_path: Path) -> None:
        client = _client("spawn", tmp_path)
        client.start()
        client.request("ping", {}, timeout=15)
        client.close()
        assert client.shutdown_receipt()["descendants_alive"] == 0

    def test_argv_artifacts_are_digest_bound(self, tmp_path: Path) -> None:
        # B6: binding the interpreter alone is not binding the candidate.
        spec = ExecutableSpec(
            path=PYTHON,
            sha256=_python_digest(),
            argv_suffix=(str(SERVER), "echo"),
            argv_digests=((str(SERVER), "0" * 64),),
        )
        client = JsonRpcStdioClient(spec=spec, scratch=tmp_path)
        with pytest.raises(JsonRpcError) as excinfo:
            client.start()
        assert excinfo.value.code == "ARTIFACT_DIGEST_MISMATCH"

    def test_correct_argv_artifact_digest_starts(self, tmp_path: Path) -> None:
        spec = ExecutableSpec(
            path=PYTHON,
            sha256=_python_digest(),
            argv_suffix=(str(SERVER), "echo"),
            argv_digests=((str(SERVER), hashlib.sha256(SERVER.read_bytes()).hexdigest()),),
        )
        client = JsonRpcStdioClient(spec=spec, scratch=tmp_path)
        client.start()
        try:
            assert client.request("ping", {}) == {"method": "ping", "params": {}}
        finally:
            client.close()
