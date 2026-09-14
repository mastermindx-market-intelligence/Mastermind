#!/usr/bin/env python3
"""Internal durable runner for one owner-prepared Workbench validation recipe.

This is not an MCP entrypoint. The Workbench process owner pre-creates a secure
state directory and passes directory descriptors plus exact argv. The runner
holds a liveness flock, captures bounded stdout/stderr itself, supervises one
process group, and durably writes one terminal receipt.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import resource
import selectors
import signal
import stat
import subprocess
import time

TERMINAL_SCHEMA = "mastermind.workbench_process_terminal.v1"
MAX_GRACE_SECONDS = 5.0
POST_EXIT_DRAIN_SECONDS = 2.0
_READ_CHUNK = 65536


def _directory(fd: int, mode: int) -> os.stat_result:
    value = os.fstat(fd)
    if (
        not stat.S_ISDIR(value.st_mode)
        or value.st_uid != os.geteuid()
        or stat.S_IMODE(value.st_mode) != mode
        or os.get_inheritable(fd) is False
    ):
        raise RuntimeError("RUNNER_DIRECTORY_REFUSED")
    return value


def _open_state_file(state_fd: int, name: str, flags: int) -> int:
    fd = os.open(
        name,
        flags | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        0o600,
        dir_fd=state_fd,
    )
    value = os.fstat(fd)
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_uid != os.geteuid()
        or stat.S_IMODE(value.st_mode) != 0o600
        or value.st_nlink != 1
    ):
        os.close(fd)
        raise RuntimeError("RUNNER_STATE_FILE_REFUSED")
    return fd


def _write_all(fd: int, raw: bytes) -> None:
    offset = 0
    while offset < len(raw):
        written = os.write(fd, raw[offset:])
        if written <= 0:
            raise OSError("short state write")
        offset += written


def _atomic_json(state_fd: int, final_name: str, document: dict[str, object]) -> None:
    raw = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii") + b"\n"
    name = f"{final_name}.tmp.{os.getpid()}"
    fd = -1
    try:
        fd = _open_state_file(state_fd, name, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        _write_all(fd, raw)
        os.fsync(fd)
    finally:
        if fd >= 0:
            os.close(fd)
    os.rename(name, final_name, src_dir_fd=state_fd, dst_dir_fd=state_fd)
    os.fsync(state_fd)


def _atomic_terminal(state_fd: int, document: dict[str, object]) -> None:
    _atomic_json(state_fd, "terminal.json", document)


def _limits() -> None:
    # Output is bounded by the wrapper pipes, not RLIMIT_FSIZE. A file-size
    # rlimit would also cap legitimate project/build artifacts created by the
    # validation command and would therefore be the wrong authority boundary.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    except (ValueError, OSError):
        pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--root-fd", type=int, required=True)
    parser.add_argument("--state-fd", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=int, required=True)
    parser.add_argument("--max-output-bytes", type=int, required=True)
    parser.add_argument("--command-id", required=True)
    parser.add_argument("argv", nargs=argparse.REMAINDER)
    return parser


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # The owner cannot supervise an inaccessible process group. Treat it as
        # unavailable here; direct-child signalling has a separate fallback.
        return False


def _close_stream(selector: selectors.BaseSelector, stream: object) -> None:
    try:
        selector.unregister(stream)
    except Exception:
        pass
    try:
        stream.close()  # type: ignore[attr-defined]
    except Exception:
        pass


def _terminal_effect(*, child_started: bool, child_receipt_durable: bool) -> str:
    if child_receipt_durable:
        return "APPLIED"
    if child_started:
        return "EFFECT_UNKNOWN"
    return "NOT_APPLIED"


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    command = list(args.argv)
    if command and command[0] == "--":
        command = command[1:]
    if (
        args.root_fd < 0
        or args.state_fd < 0
        or not command
        or not command[0].startswith("/")
        or len(args.command_id) != 32
        or any(character not in "0123456789abcdef" for character in args.command_id)
        or not 1 <= args.timeout_seconds <= 60
        or not 1024 <= args.max_output_bytes <= 4 * 1024 * 1024
    ):
        return 64

    lock_fd = stdout_fd = stderr_fd = -1
    process: subprocess.Popen[bytes] | None = None
    selector: selectors.BaseSelector | None = None
    cancel_requested = False
    timed_out = False
    output_limit = False
    unexpected_descendants = False
    grace_deadline: float | None = None
    direct_done_at: float | None = None
    stdout_bytes = 0
    stderr_bytes = 0
    child_started = False
    child_receipt_durable = False

    def signal_group(sig: int, *, cancellation: bool = False) -> None:
        nonlocal cancel_requested, grace_deadline
        if cancellation:
            cancel_requested = True
        if process is None:
            return
        signalled = False
        try:
            os.killpg(process.pid, sig)
            signalled = True
        except ProcessLookupError:
            return
        except PermissionError:
            # macOS can refuse a group signal even when the directly-owned
            # child remains signalable. Fall back to that child rather than
            # losing bounded termination entirely.
            if process.poll() is None:
                try:
                    process.send_signal(sig)
                    signalled = True
                except (ProcessLookupError, PermissionError):
                    pass
        if signalled and grace_deadline is None:
            grace_deadline = time.monotonic() + MAX_GRACE_SECONDS

    def on_signal(_signum: int, _frame: object) -> None:
        signal_group(signal.SIGTERM, cancellation=True)

    def consume(stream_name: str, raw: bytes) -> None:
        nonlocal stdout_bytes, stderr_bytes, output_limit
        if stream_name == "stdout":
            fd = stdout_fd
            used = stdout_bytes
        else:
            fd = stderr_fd
            used = stderr_bytes
        remaining = max(0, args.max_output_bytes - used)
        retained = raw[:remaining]
        if retained:
            _write_all(fd, retained)
            used += len(retained)
        if stream_name == "stdout":
            stdout_bytes = used
        else:
            stderr_bytes = used
        if len(raw) > len(retained):
            output_limit = True
            signal_group(signal.SIGTERM)

    try:
        _directory(args.root_fd, stat.S_IMODE(os.fstat(args.root_fd).st_mode))
        state_stat = _directory(args.state_fd, 0o700)
        if state_stat.st_mode & 0o077:
            raise RuntimeError("RUNNER_STATE_DIRECTORY_REFUSED")
        lock_fd = _open_state_file(
            args.state_fd, "liveness.lock", os.O_RDWR | os.O_CREAT
        )
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _atomic_json(
            args.state_fd,
            "ready.json",
            {
                "schema": "mastermind.workbench_process_ready.v1",
                "command_id": args.command_id,
                "wrapper_pid": os.getpid(),
                "ready_at_ms": int(time.time() * 1000),
            },
        )
        stdout_fd = _open_state_file(
            args.state_fd, "stdout.log", os.O_WRONLY | os.O_APPEND | os.O_CREAT
        )
        stderr_fd = _open_state_file(
            args.state_fd, "stderr.log", os.O_WRONLY | os.O_APPEND | os.O_CREAT
        )
        os.fchdir(args.root_fd)
        signal.signal(signal.SIGTERM, on_signal)
        signal.signal(signal.SIGINT, on_signal)
        env = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": "/var/empty",
            "LC_ALL": "C",
            "LANG": "C",
            "PYTHONNOUSERSITE": "1",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            close_fds=True,
            start_new_session=True,
            preexec_fn=_limits,
        )
        child_started = True
        _atomic_json(
            args.state_fd,
            "child.json",
            {
                "schema": "mastermind.workbench_process_child.v1",
                "command_id": args.command_id,
                "child_pid": process.pid,
                "started_at_ms": int(time.time() * 1000),
            },
        )
        child_receipt_durable = True
        if process.stdout is None or process.stderr is None:
            raise RuntimeError("RUNNER_PIPE_UNAVAILABLE")
        selector = selectors.DefaultSelector()
        for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, data=name)

        deadline = time.monotonic() + float(args.timeout_seconds)
        while True:
            now = time.monotonic()
            direct_code = process.poll()
            if direct_code is None and now >= deadline and not timed_out:
                timed_out = True
                signal_group(signal.SIGTERM)
            if direct_code is not None and direct_done_at is None:
                direct_done_at = now
                # Validation recipes are finite. A descendant that survives the
                # direct command is not allowed to become a daemon/orphan.
                if _group_alive(process.pid):
                    unexpected_descendants = True
                    signal_group(signal.SIGTERM)
            if grace_deadline is not None and now >= grace_deadline:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except PermissionError:
                    if process.poll() is None:
                        try:
                            process.kill()
                        except (ProcessLookupError, PermissionError):
                            pass
                grace_deadline = None

            events = selector.select(0.05)
            for key, _mask in events:
                try:
                    raw = os.read(key.fd, _READ_CHUNK)
                except BlockingIOError:
                    continue
                if raw:
                    consume(str(key.data), raw)
                else:
                    _close_stream(selector, key.fileobj)

            direct_code = process.poll()
            group_alive = _group_alive(process.pid) if direct_code is not None else True
            if direct_code is not None and not group_alive and not selector.get_map():
                break
            if (
                direct_done_at is not None
                and not group_alive
                and selector.get_map()
                and now >= direct_done_at + POST_EXIT_DRAIN_SECONDS
            ):
                # A dead process group should have closed both pipes. Refuse to
                # hang forever on an anomalous descriptor and report the runner
                # failure while preserving already-captured bounded evidence.
                unexpected_descendants = True
                for key in list(selector.get_map().values()):
                    _close_stream(selector, key.fileobj)
                break

        exit_code = process.wait()
        # Terminal effect truth is not durable until the output bytes it reports
        # are durable too.
        os.fsync(stdout_fd)
        os.fsync(stderr_fd)
        stdout_bytes = os.fstat(stdout_fd).st_size
        stderr_bytes = os.fstat(stderr_fd).st_size
        if stdout_bytes > args.max_output_bytes or stderr_bytes > args.max_output_bytes:
            raise RuntimeError("RUNNER_OUTPUT_BOUND_BROKEN")
        if timed_out:
            terminal_state = "TIMED_OUT"
        elif output_limit:
            terminal_state = "OUTPUT_LIMIT"
        elif cancel_requested:
            terminal_state = "CANCELLED"
        elif unexpected_descendants:
            terminal_state = "RUNNER_FAILED"
        else:
            terminal_state = "EXITED"
        _atomic_terminal(
            args.state_fd,
            {
                "schema": TERMINAL_SCHEMA,
                "command_id": args.command_id,
                "terminal_state": terminal_state,
                "effect_state": _terminal_effect(
                    child_started=child_started,
                    child_receipt_durable=child_receipt_durable,
                ),
                "exit_code": exit_code,
                "stdout_bytes": stdout_bytes,
                "stderr_bytes": stderr_bytes,
                "finished_at_ms": int(time.time() * 1000),
            },
        )
        return 0
    except BaseException:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                if process.poll() is None:
                    try:
                        process.kill()
                    except (ProcessLookupError, PermissionError):
                        pass
        try:
            if stdout_fd >= 0:
                os.fsync(stdout_fd)
            if stderr_fd >= 0:
                os.fsync(stderr_fd)
            stdout_bytes = os.fstat(stdout_fd).st_size if stdout_fd >= 0 else 0
            stderr_bytes = os.fstat(stderr_fd).st_size if stderr_fd >= 0 else 0
            _atomic_terminal(
                args.state_fd,
                {
                    "schema": TERMINAL_SCHEMA,
                    "command_id": args.command_id,
                    "terminal_state": "RUNNER_FAILED",
                    "effect_state": _terminal_effect(
                        child_started=child_started,
                        child_receipt_durable=child_receipt_durable,
                    ),
                    "exit_code": process.poll() if process is not None else None,
                    "stdout_bytes": min(stdout_bytes, args.max_output_bytes),
                    "stderr_bytes": min(stderr_bytes, args.max_output_bytes),
                    "finished_at_ms": int(time.time() * 1000),
                },
            )
        except BaseException:
            pass
        return 70
    finally:
        if selector is not None:
            try:
                for key in list(selector.get_map().values()):
                    _close_stream(selector, key.fileobj)
                selector.close()
            except Exception:
                pass
        for fd in (stderr_fd, stdout_fd, lock_fd):
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass


if __name__ == "__main__":
    raise SystemExit(main())
