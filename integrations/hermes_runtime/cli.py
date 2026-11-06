"""Operator entrypoint. Secrets are read from the profile's 0600 file, never from argv."""
from __future__ import annotations

import argparse
import hashlib
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

    canary_p = sub.add_parser("canary", help="Operator-only native canary within installed systemd role cgroup")
    canary_p.add_argument("--profile", type=Path, required=True)
    canary_p.add_argument("--hermes-bin", type=Path, required=True)

    text_p = sub.add_parser("text-turn", help="Host-invoked one text turn inside the installed role unit; stdin only")
    text_p.add_argument("--profile", type=Path, required=True)
    text_p.add_argument("--hermes-bin", type=Path, required=True)

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
        elif args.command == "canary":
            return _canary(args.profile, args.hermes_bin)
        elif args.command == "text-turn":
            return _text_turn(args.profile, args.hermes_bin)
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


def _prepare_installed_native(profile_path: Path, hermes_bin: Path, *, expected_role: str | None = None):
    """One existing attestation/secret owner shared by canary and text helper.

    Caller is a fresh single-threaded process in the original role system unit.
    This function installs no service or identity and invokes no model.
    """
    from .constants import MANIFEST_SCHEMA, PINNED_UPSTREAM_SHA
    from .install import assert_checkout_sha
    from integrations.hermes_harness.native_turn_runner import assert_role_service_cgroup

    profile = load_profile(profile_path)
    if expected_role is not None and profile.role != expected_role:
        raise RuntimeRefusal("NATIVE_TEXT_ROLE_MISMATCH")
    state = profile.state_dir
    expected_profile = state / "current" / "profile.yaml"
    expected_bin = state / "current" / "bin" / "hermes"
    if (not profile_path.is_absolute() or profile_path != expected_profile
            or not hermes_bin.is_absolute() or hermes_bin != expected_bin
            or profile.sha != PINNED_UPSTREAM_SHA):
        raise RuntimeRefusal("CANARY_NOT_INSTALLED_ROLE")
    # The local operator must route through the actual unit; no out-of-cgroup
    # invocation may even read a provider credential.
    assert_role_service_cgroup(profile.role)
    from .system_service import assert_role_network_profile
    assert_role_network_profile(profile)
    from .role_isolation import assert_role_credential_isolation
    from .tcp_sandbox import enforce_role_tcp_ports
    assert_role_credential_isolation(profile)
    enforce_role_tcp_ports(profile)
    current = state / "current"
    manifest_path = state / "install-manifest.json"
    receipt_path = current / "install-receipt.json"
    native_config = profile.hermes_home / "profiles" / profile.role / "config.yaml"
    if (not current.is_symlink() or manifest_path.is_symlink()
            or receipt_path.is_symlink() or profile_path.is_symlink()
            or native_config.is_symlink() or not native_config.is_file()
            or not manifest_path.is_file() or not receipt_path.is_file()):
        raise RuntimeRefusal("CANARY_INSTALL_NOT_ATTESTED")
    try:
        release = current.readlink()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        saved_profile = profile_path.read_bytes()
        saved_native = native_config.read_bytes()
    except (OSError, ValueError, UnicodeError):
        raise RuntimeRefusal("CANARY_INSTALL_NOT_ATTESTED") from None
    if (not 0 < len(saved_profile) <= 64 * 1024
            or not 0 < len(saved_native) <= 64 * 1024):
        raise RuntimeRefusal("CANARY_INSTALL_NOT_ATTESTED")
    if (release.parts[:1] != ("releases",) or len(release.parts) != 2
            or not release.parts[1].isdigit()
            or not isinstance(manifest, dict) or not isinstance(receipt, dict)
            or manifest.get("schema") != MANIFEST_SCHEMA
            or manifest.get("owns_state_dir") is not True
            or manifest.get("current_release") != release.parts[1]
            or manifest.get("state_dir") != str(state)
            or manifest.get("service_name") != profile.service_name
            or manifest.get("secrets_file") != str(profile.secrets_file)
            or manifest.get("sha") != PINNED_UPSTREAM_SHA
            or receipt.get("upstream_attested") is not True
            or receipt.get("status") != "RELEASE_WRITTEN"
            or receipt.get("role") != profile.role
            or receipt.get("sha") != PINNED_UPSTREAM_SHA
            or receipt.get("profile_sha256") != hashlib.sha256(saved_profile).hexdigest()
            or receipt.get("hermes_config_sha256") != hashlib.sha256(saved_native).hexdigest()):
        raise RuntimeRefusal("CANARY_INSTALL_NOT_ATTESTED")
    assert_checkout_sha(current / "upstream")
    secrets = load_secrets(profile.secrets_file)
    runtime = ServiceRuntime(profile, secrets, hermes_bin)
    source_env = runtime._model_child_env()
    from integrations.hermes_models.contract import native_provider
    spec = native_provider(profile.role, profile.native_provider_id)
    # The normal serving child currently also receives dashboard identity.
    # This one-shot text check needs only one model key and the approved
    # proxy; never forward dashboard Basic Auth or Slack IDs to the canary.
    canary_keys = {
        "PATH", "HOME", "HERMES_HOME", "LANG", "HTTPS_PROXY", "NO_PROXY",
        spec.credential_env,
    }
    model_env = {key: value for key, value in source_env.items() if key in canary_keys}
    return profile, model_env


def _canary(profile_path: Path, hermes_bin: Path) -> int:
    from integrations.hermes_harness.native_turn_runner import run_native_canary
    profile, model_env = _prepare_installed_native(profile_path, hermes_bin)
    receipt = run_native_canary(profile, hermes_bin=hermes_bin, model_child_env=model_env)
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == "PASS_CHILD_OUTPUT_OBSERVATION_ONLY" else POLICY_EXIT


def _text_turn(profile_path: Path, hermes_bin: Path) -> int:
    """Private stdout pipe to the existing host consumer, never a Slack sender.

    Explicit invocation can spend provider credits. Install/status/health do
    not invoke it. All admission, budget and current native-writer authority
    remain with the existing authenticated parent; this is not a public API.
    """
    from integrations.hermes_harness.native_text import (
        MAX_PROMPT_BYTES, canonical_text_prompt, execute_prepared_text, text_result,
    )
    from .errors import NativeTurnEffectUnknown
    try:
        raw = sys.stdin.buffer.read(MAX_PROMPT_BYTES + 1)
        if not raw or len(raw) > MAX_PROMPT_BYTES:
            raise RuntimeRefusal("NATIVE_TEXT_PROMPT_INVALID")
        role, prompt = canonical_text_prompt(raw.decode("utf-8", "strict"))
        profile, model_env = _prepare_installed_native(profile_path, hermes_bin, expected_role=role)
    except (RuntimeRefusal, OSError, UnicodeError, ValueError):
        print(json.dumps(text_result("REFUSED"), sort_keys=True))
        return 2
    try:
        answer = execute_prepared_text(profile, hermes_bin=hermes_bin, model_env=model_env, prompt=prompt)
    except NativeTurnEffectUnknown:
        print(json.dumps(text_result("EFFECT_UNKNOWN"), sort_keys=True))
        return 3
    except RuntimeRefusal:
        # Prepared-prompt/env validation refused before native invocation.
        print(json.dumps(text_result("REFUSED"), sort_keys=True))
        return 2
    print(json.dumps(text_result("TEXT_READY", text=answer), sort_keys=True))
    return 0



def _supervise(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile, state_dir=args.state, secrets_file=args.secrets_file)
    # systemd --user cannot attach IPAddressDeny eBPF on Ubuntu1. Never read
    # a provider credential or spawn Hermes from that ineffective manager.
    # Only PID1's exact system.slice service cgroup is an eligible process.
    from .system_service import assert_root_service_cgroup, assert_role_network_profile
    try:
        assert_root_service_cgroup(profile.role)
        assert_role_network_profile(profile)
        from .role_isolation import assert_role_credential_isolation
        from .tcp_sandbox import enforce_role_tcp_ports
        assert_role_credential_isolation(profile)
        enforce_role_tcp_ports(profile)
        from .role_status_publisher import publisher_from_process
        publisher = publisher_from_process(profile)
    except RuntimeRefusal as exc:
        print(exc.code, file=sys.stderr)
        return CONFIG_EXIT
    secrets = load_secrets(profile.secrets_file)
    runtime = ServiceRuntime(profile, secrets, args.hermes_bin, role_status_publisher=publisher)
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
