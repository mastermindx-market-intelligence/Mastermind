#!/usr/bin/env python3
"""Internal durable runner for one owner-prepared Workbench validation recipe.

This is not an MCP entrypoint. The Workbench process owner pre-creates a secure
state directory and passes directory descriptors plus exact argv. The runner
holds a liveness flock, redirects bounded output to that directory, supervises
one process group, and durably writes one terminal receipt.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
import resource
import signal
import stat
import subprocess
import sys
import time

TERMINAL_SCHEMA = "mastermind.workbench_process_terminal.v1"
MAX_GRACE_SECONDS = 5.0


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


def _limits(max_output_bytes: int) -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (max_output_bytes, max_output_bytes))
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
    cancel_requested = False
    timed_out = False
    grace_deadline: float | None = None

    def terminate_group(sig: int) -> None:
        nonlocal cancel_requested, grace_deadline
        cancel_requested = True
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                return
            if grace_deadline is None:
                grace_deadline = time.monotonic() + MAX_GRACE_SECONDS

    def on_signal(_signum: int, _frame: object) -> None:
        terminate_group(signal.SIGTERM)

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
            stdout=stdout_fd,
            stderr=stderr_fd,
            env=env,
            close_fds=True,
            start_new_session=True,
            preexec_fn=lambda: _limits(args.max_output_bytes),
        )
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
        deadline = time.monotonic() + float(args.timeout_seconds)
        while process.poll() is None:
            now = time.monotonic()
            if now >= deadline and not timed_out:
                timed_out = True
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                grace_deadline = now + MAX_GRACE_SECONDS
            if grace_deadline is not None and now >= grace_deadline and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                grace_deadline = None
            time.sleep(0.05)
        exit_code = process.wait()
        stdout_bytes = os.fstat(stdout_fd).st_size
        stderr_bytes = os.fstat(stderr_fd).st_size
        if timed_out:
            terminal_state = "TIMED_OUT"
        elif cancel_requested:
            terminal_state = "CANCELLED"
        elif stdout_bytes >= args.max_output_bytes or stderr_bytes >= args.max_output_bytes:
            terminal_state = "OUTPUT_LIMIT"
        else:
            terminal_state = "EXITED"
        _atomic_terminal(
            args.state_fd,
            {
                "schema": TERMINAL_SCHEMA,
                "command_id": args.command_id,
                "terminal_state": terminal_state,
                "exit_code": exit_code,
                "stdout_bytes": stdout_bytes,
                "stderr_bytes": stderr_bytes,
                "finished_at_ms": int(time.time() * 1000),
            },
        )
        return 0
    except BaseException:
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            stdout_bytes = os.fstat(stdout_fd).st_size if stdout_fd >= 0 else 0
            stderr_bytes = os.fstat(stderr_fd).st_size if stderr_fd >= 0 else 0
            _atomic_terminal(
                args.state_fd,
                {
                    "schema": TERMINAL_SCHEMA,
                    "command_id": args.command_id,
                    "terminal_state": "RUNNER_FAILED",
                    "exit_code": None,
                    "stdout_bytes": stdout_bytes,
                    "stderr_bytes": stderr_bytes,
                    "finished_at_ms": int(time.time() * 1000),
                },
            )
        except BaseException:
            pass
        return 70
    finally:
        for fd in (stderr_fd, stdout_fd, lock_fd):
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass


if __name__ == "__main__":
    raise SystemExit(main())
