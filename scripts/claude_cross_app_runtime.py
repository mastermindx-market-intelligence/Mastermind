"""Guarded launcher for the four isolated Claude macOS app profiles.

This utility is an entry adapter only. It does not own session identity, messaging,
lifecycle, account state, authentication, retries, or Mastermind RuntimeBinding.
It reuses one known Claude Desktop runtime with the existing isolated Parall
user-data roots and refuses concurrent launches of an already-running profile.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
import subprocess
from typing import Any

MODERN_RUNTIME = "/Users/chriswong/Applications/Mastermind Claude Runtime/Claude.app"
PROFILE_ROOTS: dict[str, str] = {
    "claude-2": "/Users/chriswong/Library/Application Support/Parall/Claude 2",
    "claude-3": "/Users/chriswong/Library/Application Support/Parall/Claude 3",
    "claude-5": "/Users/chriswong/Library/Application Support/Parall/Claude 5",
    "claude-6": "/Users/chriswong/Library/Application Support/Parall/Claude 6",
}


@dataclasses.dataclass(frozen=True, slots=True)
class ProfileStatus:
    profile: str
    running_pids: tuple[int, ...]
    send_message_denied: bool


def _profile_root(profile: str) -> str:
    try:
        return PROFILE_ROOTS[profile]
    except (KeyError, TypeError):
        raise ValueError("unsupported profile") from None


def build_launch_argv(profile: str) -> tuple[str, ...]:
    root = _profile_root(profile)
    return (
        "/usr/bin/open",
        "-na",
        MODERN_RUNTIME,
        "--args",
        f"--user-data-dir={root}",
    )


def profile_status_from_process_rows(
    profile: str,
    rows: Iterable[tuple[int, str]],
) -> ProfileStatus:
    root = _profile_root(profile)
    matched: list[tuple[int, str]] = []
    for pid, command in rows:
        if not isinstance(pid, int) or not isinstance(command, str):
            continue
        if root in command:
            matched.append((pid, command))
    return ProfileStatus(
        profile=profile,
        running_pids=tuple(sorted({pid for pid, _ in matched})),
        send_message_denied=any(
            "--disallowedTools SendMessage" in command for _, command in matched
        ),
    )


def safe_status_document(
    profile: str,
    rows: Iterable[tuple[int, str]],
    *,
    desktop_version: str,
) -> dict[str, Any]:
    status = profile_status_from_process_rows(profile, rows)
    return {
        "profile": profile,
        "profile_root": _profile_root(profile),
        "desktop_version": desktop_version,
        "running_count": len(status.running_pids),
        "send_message_denied": status.send_message_denied,
        "launch_allowed_now": not status.running_pids,
    }


def launch_profile(
    profile: str,
    process_rows: Iterable[tuple[int, str]],
    *,
    runner: Callable[[Sequence[str]], object],
    runtime_exists: bool,
) -> dict[str, Any]:
    status = profile_status_from_process_rows(profile, process_rows)
    if status.running_pids:
        raise RuntimeError("PROFILE_ALREADY_RUNNING")
    if not runtime_exists:
        raise RuntimeError("MODERN_RUNTIME_UNAVAILABLE")
    argv = build_launch_argv(profile)
    runner(argv)
    return {
        "profile": profile,
        "effect": "LAUNCH_REQUESTED",
        "launch_allowed_now": True,
    }


def _process_rows() -> list[tuple[int, str]]:
    result = subprocess.run(
        ["ps", "-axo", "pid=,command="],
        check=True,
        capture_output=True,
        text=True,
    )
    rows: list[tuple[int, str]] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, sep, command = stripped.partition(" ")
        if not sep:
            continue
        try:
            pid = int(pid_text)
        except ValueError:
            continue
        rows.append((pid, command.lstrip()))
    return rows


def _desktop_version() -> str:
    plist = Path(MODERN_RUNTIME) / "Contents/Info.plist"
    result = subprocess.run(
        ["/usr/bin/plutil", "-extract", "CFBundleShortVersionString", "raw", str(plist)],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect or launch one approved isolated Claude profile."
    )
    parser.add_argument("action", choices=("status", "launch"))
    parser.add_argument("profile", choices=tuple(PROFILE_ROOTS))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    rows = _process_rows()
    if args.action == "status":
        print(
            json.dumps(
                safe_status_document(
                    args.profile,
                    rows,
                    desktop_version=_desktop_version(),
                ),
                sort_keys=True,
            )
        )
        return 0

    status = profile_status_from_process_rows(args.profile, rows)
    if status.running_pids:
        raise SystemExit("PROFILE_ALREADY_RUNNING")
    runtime_exists = Path(MODERN_RUNTIME).is_dir()
    if not runtime_exists:
        raise SystemExit("MODERN_RUNTIME_UNAVAILABLE")
    if args.dry_run:
        print(
            json.dumps(
                {
                    "profile": args.profile,
                    "effect": "DRY_RUN",
                    "launch_allowed_now": True,
                },
                sort_keys=True,
            )
        )
        return 0
    result = launch_profile(
        args.profile,
        rows,
        runner=lambda command: subprocess.run(command, check=True),
        runtime_exists=True,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
