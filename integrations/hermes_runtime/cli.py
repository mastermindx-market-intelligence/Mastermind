"""Operator entrypoint. Secrets are read from the profile's 0600 file, never from argv."""
from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
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


def main(argv: list[str] | None = None, *,
         custody_observer: Callable[[], Mapping[str, object]] | None = None,
         native_launch=None) -> int:
    """Run one operator command.

    ``custody_observer`` is the private in-process dependency of the main
    supervisor: a plain callable supplied by the caller, never a CLI flag, an
    environment variable, a serialized callback, a model output or a separate
    configuration field.  It is handed unchanged to the supervisor's existing
    publisher construction; no other command consumes it.
    """
    parser = argparse.ArgumentParser(prog="hermes-runtime")
    sub = parser.add_subparsers(dest="command", required=True)

    install_p = sub.add_parser("install", help="Install or upgrade the pinned user runtime")
    install_p.add_argument("--profile", type=Path, required=True)
    install_p.add_argument("--state", type=Path, required=True)
    install_p.add_argument("--systemd-user-dir", type=Path, required=True)
    install_p.add_argument("--secrets-file", type=Path, required=True)
    install_p.add_argument("--hermes-bin", type=Path, required=True)
    install_p.add_argument("--native-installation", type=Path,
                           help="Frozen native member selected by the installed release owner")
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

    enroll_p = sub.add_parser("enroll-secretary-session", help="Enroll the frozen native Secretary session in its installed role")
    enroll_p.add_argument("--profile", type=Path, required=True)
    enroll_p.add_argument("--hermes-bin", type=Path, required=True)

    meta_enroll_p = sub.add_parser("enroll-meta-session", help="Enroll the frozen native Meta-CEO session in its installed role")
    meta_enroll_p.add_argument("--profile", type=Path, required=True)
    meta_enroll_p.add_argument("--hermes-bin", type=Path, required=True)

    for command, help_text in (
            ("eval-submit", "Admit one selected evaluation on the enrolled native session; stdin only"),
            ("eval-read", "Read the exact original evaluation identity once; stdin only"),
            ("eval-publish", "Publish one terminal original evaluation without inference; stdin only"),
            ("eval-trial", "Read consumption eligibility of an already published original trial; stdin only")):
        evaluation_p = sub.add_parser(command, help=help_text)
        evaluation_p.add_argument("--profile", type=Path, required=True)
        evaluation_p.add_argument("--hermes-bin", type=Path, required=True)

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
            native = None
            if args.native_installation is not None:
                from ops.executive_os.release_manifest import _closed_json, ReleaseManifestError
                with args.native_installation.open("rb") as stream:
                    raw = stream.read(16385)
                if len(raw) > 16384:
                    raise RuntimeRefusal("NATIVE_INSTALLATION_TOO_LARGE")
                try:
                    native = _closed_json(raw)
                except (ReleaseManifestError, ValueError):
                    raise RuntimeRefusal("NATIVE_INSTALLATION_INVALID") from None
            payload = install(
                profile_path=args.profile,
                state_dir=args.state,
                systemd_user_dir=args.systemd_user_dir,
                secrets_file=args.secrets_file,
                hermes_bin=args.hermes_bin,
                upstream_source=args.upstream_source,
                fetch=args.fetch,
                native_installation=native,
            )
        elif args.command == "uninstall":
            payload = uninstall(state_dir=args.state, systemd_user_dir=args.systemd_user_dir)
        elif args.command == "rollback":
            payload = rollback(args.state)
        elif args.command == "check-registry":
            payload = _check(args.profile, args.tool_list, args.stderr)
        elif args.command == "supervise":
            kwargs = {"custody_observer": custody_observer}
            if native_launch is not None:
                kwargs["native_launch"] = native_launch
            return _supervise(args, **kwargs)
        elif args.command == "canary":
            return _canary(args.profile, args.hermes_bin)
        elif args.command == "enroll-secretary-session":
            return _enroll_secretary_session(args.profile, args.hermes_bin, native_launch=native_launch)
        elif args.command == "enroll-meta-session":
            return _enroll_meta_session(args.profile, args.hermes_bin, native_launch=native_launch)
        elif args.command in {"eval-submit", "eval-read", "eval-publish", "eval-trial"}:
            return _native_evaluation(args.profile, args.hermes_bin,
                operation=args.command.removeprefix("eval-"), native_launch=native_launch)
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
    if profile.gateway_backend == "native-session-authority":
        raise RuntimeRefusal("NATIVE_CANARY_REQUIRES_SESSION_OWNER")
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



def _enroll_secretary_session(profile_path: Path, hermes_bin: Path, *, native_launch=None) -> int:
    return _enroll_native_session(profile_path, hermes_bin, expected_role="mmsecretary",
                                 native_launch=native_launch)


def _enroll_meta_session(profile_path: Path, hermes_bin: Path, *, native_launch=None) -> int:
    return _enroll_native_session(profile_path, hermes_bin, expected_role="mmmeta",
                                 native_launch=native_launch)


def _prepare_native_operator(profile_path: Path, hermes_bin: Path, *, expected_role: str,
                           native_launch=None):
    """Share the original held role/owner fences; create no session or admission."""
    import asyncio
    from contextlib import asynccontextmanager
    from .constants import conversation_contract
    conversation_contract(expected_role)
    from .constants import PINNED_UPSTREAM_SHA
    from .native_session_control import (
        NativeSecretaryClient, _implementation, validate_enrollment_capability,
    )
    from .native_gateway_entry import prepare_vendor, _CAPABILITIES
    from .system_service import assert_root_service_cgroup, assert_role_network_profile
    from .role_isolation import assert_role_credential_isolation
    from .tcp_sandbox import enforce_role_tcp_ports, role_tcp_ports
    from .supervisor import expected_disabled_mcp
    from .profile import dump_profile
    from ops.executive_os.hermes_role_metadata_observer import (
        _HeldRoleQualification, _query_fixed_pid1, _boot_id,
    )

    if native_launch is None:
        raise RuntimeRefusal("NATIVE_ENROLLMENT_HELD_LAUNCH_REQUIRED")
    profile = load_profile(profile_path)
    if (profile.role != expected_role or profile.gateway_backend != "native-session-authority"
            or profile.sha != PINNED_UPSTREAM_SHA
            or profile_path != profile.state_dir / "current/profile.yaml"
            or not profile_path.is_absolute()
            or native_launch.recipe.get("schema") not in (
                "mastermind.hermes_native_gateway_installation/v2",
                "mastermind.hermes_native_gateway_installation/v3",
                "mastermind.hermes_native_gateway_installation/v4")):
        raise RuntimeRefusal("NATIVE_ENROLLMENT_INSTALLATION_REQUIRED")
    # These existing v2/v3 recipes require a closed enrollment descriptor.
    # Structural validation creates no enrollment and historical EVAL never
    # requires its current session tip to equal the original attempt.
    validate_enrollment_capability(native_launch.recipe.get("session_enrollment"), role=expected_role)
    implementation_sha = native_launch.owner.root.name
    # Validate identities before native imports; the release entry owns their
    # exact dependency roots, interpreter and source descriptors.
    _implementation(implementation_sha)
    saved_profile = dump_profile(profile)

    def qualify_profile():
        current = load_profile(profile_path)
        if dump_profile(current) != saved_profile:
            raise RuntimeRefusal("NATIVE_ENROLLMENT_PROFILE_CHANGED")
        native_launch.qualify(current, hermes_bin)
        assert_root_service_cgroup(current.role)
        assert_role_network_profile(current)
        assert_role_credential_isolation(current)
        primary = native_launch.recipe.get("primary_application")
        evaluation_inputs = native_launch.recipe.get("evaluation_inputs")
        role_tcp_ports(current, primary_application=primary)
        if primary is not None:
            expected_disabled_mcp(
                current, native_launch.recipe.get("executive_consumer"), primary,
                evaluation_inputs=evaluation_inputs)
        else:
            expected_disabled_mcp(
                current, native_launch.recipe.get("executive_consumer"),
                evaluation_inputs=evaluation_inputs)

    qualify_profile()
    # Landlock attaches once while this entry is still single-threaded and
    # before asyncio creates a loop or executor. Children inherit it. Owner
    # rechecks below retain the exact profile and must not reattach policy.
    primary = native_launch.recipe.get("primary_application")
    enforce_role_tcp_ports(
        profile, **({"native_launch": native_launch} if primary is not None else {}))
    home = (profile.hermes_home.resolve(strict=True) / "profiles" / profile.role).resolve(strict=True)
    prepare_vendor(Path(native_launch.recipe["vendor_root"]))
    from hermes_cli.gateway_runtime_discovery import query_identify
    from hermes_cli.gateway_runtime import _endpoint

    @asynccontextmanager
    async def connected():
        with _HeldRoleQualification(implementation_sha) as held:
            async def owner():
                qualify_profile()
                if (profile.hermes_home.resolve(strict=True) / "profiles" / profile.role).resolve(strict=True) != home:
                    raise RuntimeRefusal("NATIVE_ENROLLMENT_PROFILE_HOME_CHANGED")
                boot = _boot_id()
                rows = await asyncio.wait_for(_query_fixed_pid1(role=expected_role), timeout=3)
                if len(rows) != 1 or rows[0]["role"] != expected_role:
                    raise RuntimeRefusal("NATIVE_ENROLLMENT_SUPERVISOR_UNQUALIFIED")
                facts = held.role_facts(expected_role, rows[0]["unit_properties"], boot)
                payload = await asyncio.to_thread(query_identify, home, timeout=2)
                if (type(payload) is not dict or type(payload.get("pid")) is not int
                        or payload["pid"] <= 0 or payload.get("hermes_home") != str(home)):
                    raise RuntimeRefusal("NATIVE_ENROLLMENT_OWNER_UNQUALIFIED")
                observed = _endpoint(payload, home)
                endpoint = observed.endpoint
                if (observed.state != "ready" or endpoint is None
                        or endpoint.profile_id != str(home)
                        or endpoint.code_sha != PINNED_UPSTREAM_SHA
                        or type(endpoint.authority_epoch) is not int or endpoint.authority_epoch < 1
                        or type(endpoint.instance_id) is not str or not endpoint.instance_id
                        or endpoint.runtime_protocol != 1 or endpoint.supervisor != "external"
                        or endpoint.api_origin != f"http://{profile.gateway_host}:{profile.backend_port}"
                        or not _CAPABILITIES <= endpoint.capabilities):
                    raise RuntimeRefusal("NATIVE_ENROLLMENT_OWNER_UNQUALIFIED")
                child = native_launch.observe_child(payload["pid"])
                if (child["parent_pid"] != facts["main_pid"]
                        or child["boot_id"] != facts["boot_id"] or child["boot_id"] != boot):
                    raise RuntimeRefusal("NATIVE_ENROLLMENT_OWNER_LINEAGE_CHANGED")
                if _boot_id() != boot:
                    raise RuntimeRefusal("NATIVE_ENROLLMENT_OWNER_CHANGED")
                held.check()
                native_launch.check()
                stable_facts = {key: value for key, value in facts.items() if key != "gateway_listener"}
                return {
                    "supervisor": stable_facts,
                    "child": {"pid": payload["pid"], **{key: child[key] for key in
                              ("parent_pid", "boot_id", "start_identity")}},
                    "endpoint": {key: getattr(endpoint, key) for key in (
                        "profile_id", "instance_id", "authority_epoch", "code_sha",
                        "runtime_protocol", "supervisor", "api_origin")},
                }

            before = await owner()
            client = NativeSecretaryClient(home, expected_pid=before["child"]["pid"], role=expected_role)
            yield client, before, owner

    return profile, home, implementation_sha, connected


def _enroll_native_session(profile_path: Path, hermes_bin: Path, *, expected_role: str,
                           native_launch=None) -> int:
    """One held-release, in-cgroup enrollment of the frozen native original."""
    import asyncio
    from .native_session_control import (
        enrollment_result, validate_enrollment_capability, validate_enrollment_result,
    )
    if native_launch is None:
        raise RuntimeRefusal("NATIVE_ENROLLMENT_HELD_LAUNCH_REQUIRED")
    profile, home, implementation_sha, connected = _prepare_native_operator(
        profile_path, hermes_bin, expected_role=expected_role, native_launch=native_launch)
    capability = validate_enrollment_capability(native_launch.recipe.get("session_enrollment"), role=expected_role)
    request_id = capability["request_id"]

    def result(status):
        return enrollment_result(implementation_sha, request_id, status, role=expected_role)

    async def execute():
        modifying = False
        try:
            async with connected() as (client, before, owner):
                observed = await asyncio.to_thread(client.inspect_enrollment, implementation_sha, request_id)
                # This also serves as the fresh, immediately pre-create fence.
                if await owner() != before:
                    return result("UNAVAILABLE")
                if observed["status"] == "ABSENT":
                    modifying = True
                    observed = await asyncio.to_thread(client.enroll_session, implementation_sha, request_id)
                    if await owner() != before:
                        return result("EFFECT_UNKNOWN")
                observed = validate_enrollment_result(
                    observed, implementation_sha=implementation_sha, request_id=request_id,
                    profile_id=str(home), principal_id=f"uid:{native_launch.row['uid']}", role=expected_role)
                if observed["status"] == "ENROLLED" and any(
                        observed["target"][key] != before["endpoint"][key]
                        for key in ("profile_id", "instance_id", "authority_epoch")):
                    return result("EFFECT_UNKNOWN" if modifying else "UNAVAILABLE")
                return observed
        except Exception:
            return result("EFFECT_UNKNOWN" if modifying else "UNAVAILABLE")

    value = asyncio.run(execute())
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))
    if value["status"] == "ENROLLED":
        return 0
    return 3 if value["status"] == "EFFECT_UNKNOWN" else POLICY_EXIT

def _native_evaluation(profile_path: Path, hermes_bin: Path, *, operation: str, native_launch=None) -> int:
    """One attended operation; input bodies stay off argv and out of receipts."""
    import asyncio
    from .native_eval_operator import (
        MAX_REQUEST_BYTES, parse_request, recovery_for, result, execute,
    )
    recovery = None
    try:
        request = parse_request(operation, sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1))
        if operation != "submit":
            recovery = request
        profile, home, implementation, connected = _prepare_native_operator(
            profile_path, hermes_bin, expected_role="mmmeta", native_launch=native_launch)
        recovery = recovery_for(operation, request, home)
    except Exception:
        value = result(operation, "REFUSED", recovery=recovery, reason="EVALUATION_OPERATOR_PREFLIGHT_REFUSED")
    else:
        try:
            value = asyncio.run(execute(operation, request, recovery=recovery, profile=profile,
                home=home, implementation=implementation, native_launch=native_launch, connected=connected))
        except (Exception, KeyboardInterrupt):
            # asyncio.run may fail during shutdown after the native call has
            # committed. The inner coroutine cannot classify that outer loss.
            value = result(operation, "UNAVAILABLE" if operation in {"read", "trial"} else "EFFECT_UNKNOWN",
                recovery=recovery, reason="EVALUATION_OPERATOR_RUNNER_RECONCILIATION_REQUIRED")
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))
    if value["status"] in {"ADMITTED", "OBSERVED", "PUBLISHED", "TRIAL_OBSERVED"}:
        return 0
    return 3 if value["status"] == "EFFECT_UNKNOWN" else POLICY_EXIT



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



def _supervise(args: argparse.Namespace, *,
               custody_observer: Callable[[], Mapping[str, object]] | None = None,
               native_launch=None) -> int:
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
        enforce_role_tcp_ports(profile, **({"native_launch": native_launch}
            if profile.model_provider == "mastermind-fabric" else {}))
        from .role_status_publisher import publisher_from_process
        publisher = publisher_from_process(profile, custody_observer=custody_observer)
        if profile.gateway_backend == "native-session-authority":
            if native_launch is None:
                raise RuntimeRefusal("NATIVE_STARTUP_CUSTODY_REQUIRED")
            try:
                native_launch.qualify(profile, args.hermes_bin)
            except RuntimeRefusal:
                raise
            except Exception:
                raise RuntimeRefusal("NATIVE_STARTUP_CUSTODY_UNQUALIFIED") from None
    except RuntimeRefusal as exc:
        print(exc.code, file=sys.stderr)
        return CONFIG_EXIT
    secrets = load_secrets(profile.secrets_file)
    runtime_kwargs = {"role_status_publisher": publisher}
    if native_launch is not None:
        runtime_kwargs["native_launch"] = native_launch
    runtime = ServiceRuntime(profile, secrets, args.hermes_bin, **runtime_kwargs)
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

