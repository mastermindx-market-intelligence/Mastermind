"""Operator entrypoint. Secrets are read from the profile's 0600 file, never from argv."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import signal
import sys
import time

from .constants import CONFIG_EXIT, IO_EXIT, POLICY_EXIT, REGISTRY_SCHEMA
from .errors import RuntimeRefusal
from .install import install, rollback, uninstall
from .profile import load_profile
from .registry import assert_registered_tools_exact, extension_tools_for
from .secrets import load_secrets
from .supervisor import ServiceRuntime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hermes-runtime")
    sub = parser.add_subparsers(dest="command", required=True)

    install_p = sub.add_parser("install", help="Install or upgrade the pinned user runtime")
    install_p.add_argument("--profile", type=Path, required=True)
    install_p.add_argument("--state", type=Path, required=True)
    install_p.add_argument("--systemd-user-dir", type=Path, required=True)
    install_p.add_argument("--secrets-file", type=Path, required=True)
    install_p.add_argument("--hermes-bin", type=Path, required=True)
    source = install_p.add_mutually_exclusive_group(required=True)
    source.add_argument("--upstream-source", type=Path)
    source.add_argument("--fetch", action="store_true")

    uninstall_p = sub.add_parser("uninstall", help="Remove the runtime state and user unit")
    uninstall_p.add_argument("--state", type=Path, required=True)
    uninstall_p.add_argument("--systemd-user-dir", type=Path, required=True)

    rollback_p = sub.add_parser("rollback", help="Point current at the previous release")
    rollback_p.add_argument("--state", type=Path, required=True)

    supervise_p = sub.add_parser("supervise", help="Run the loopback supervisor in the foreground")
    supervise_p.add_argument("--profile", type=Path, required=True)
    supervise_p.add_argument("--hermes-bin", type=Path, required=True)
    supervise_p.add_argument("--state", type=Path)
    supervise_p.add_argument("--secrets-file", type=Path)

    check_p = sub.add_parser("check-registry", help="Require allowlist == registered tools and empty stderr")
    check_p.add_argument("--profile", type=Path, required=True)
    check_p.add_argument("--tool-list", type=Path, required=True)
    check_p.add_argument("--stderr", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            payload = install(
                profile_path=args.profile,
                state_dir=args.state,
                systemd_user_dir=args.systemd_user_dir,
                secrets_file=args.secrets_file,
                hermes_bin=args.hermes_bin,
                upstream_source=args.upstream_source,
                fetch=args.fetch,
            )
        elif args.command == "uninstall":
            payload = uninstall(state_dir=args.state, systemd_user_dir=args.systemd_user_dir)
        elif args.command == "rollback":
            payload = rollback(args.state)
        elif args.command == "check-registry":
            payload = _check(args.profile, args.tool_list, args.stderr)
        elif args.command == "supervise":
            return _supervise(args)
        else:
            raise RuntimeRefusal("COMMAND_INVALID")
    except RuntimeRefusal as exc:
        print(exc.code, file=sys.stderr)
        return POLICY_EXIT
    except OSError:
        print("RUNTIME_IO_FAILURE", file=sys.stderr)
        return IO_EXIT
    print(json.dumps(payload, sort_keys=True))
    return 0


def _check(profile_path: Path, tool_list: Path, stderr_path: Path) -> dict:
    profile = load_profile(profile_path)
    if tool_list.stat().st_size > 96 * 1024 or stderr_path.stat().st_size > 96 * 1024:
        raise RuntimeRefusal("REGISTRY_INPUT_TOO_LARGE")
    result = assert_registered_tools_exact(
        tool_list.read_text(encoding="utf-8"),
        stderr_path.read_bytes(),
        profile.tool_allowlist,
        extension_tools_for(profile),
    )
    if result["schema"] != REGISTRY_SCHEMA:
        raise RuntimeRefusal("REGISTRY_SCHEMA_MISMATCH")
    return result


def _supervise(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile, state_dir=args.state, secrets_file=args.secrets_file)
    secrets = load_secrets(profile.secrets_file)
    runtime = ServiceRuntime(profile, secrets, args.hermes_bin)
    try:
        runtime.start()
    except RuntimeRefusal as exc:
        print(exc.code, file=sys.stderr)
        return CONFIG_EXIT
    stop = False

    def handle(signum: int, frame: object) -> None:
        nonlocal stop
        stop = True
        runtime.stop()

    signal.signal(signal.SIGTERM, handle)
    signal.signal(signal.SIGINT, handle)
    while not stop and not runtime.failed:
        time.sleep(0.2)
    runtime.stop()
    if runtime.refusal_code:
        print(runtime.refusal_code, file=sys.stderr)
        return CONFIG_EXIT
    if runtime.failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
