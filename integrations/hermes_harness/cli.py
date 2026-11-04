"""``hermesctl`` commands. Secrets stay in 0600 files and off argv."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from integrations.hermes_harness.doctor import doctor, format_doctor
from integrations.hermes_harness.overlays import overlay_chain, render_overlays
from integrations.hermes_harness.stack import write_composed_profile
from integrations.hermes_harness.tick import FIXTURE, routine_tick
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.install import install as runtime_install
from integrations.hermes_runtime.install import uninstall as runtime_uninstall
from integrations.hermes_runtime.profile import load_profile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hermesctl")
    sub = parser.add_subparsers(dest="command", required=True)

    install_p = sub.add_parser("install")
    install_p.add_argument("--role", choices=("mmsecretary", "mmmeta"), required=True)
    install_p.add_argument("--state", type=Path, required=True)
    install_p.add_argument("--systemd-user-dir", type=Path, required=True)
    install_p.add_argument("--secrets-file", type=Path, required=True)
    install_p.add_argument("--hermes-bin", type=Path, required=True)
    install_p.add_argument("--model-provider", help="One existing role-eligible native provider id; no automatic fallback")
    source = install_p.add_mutually_exclusive_group(required=True)
    source.add_argument("--upstream-source", type=Path)
    source.add_argument("--fetch", action="store_true")

    uninstall_p = sub.add_parser("uninstall")
    uninstall_p.add_argument("--state", type=Path, required=True)
    uninstall_p.add_argument("--systemd-user-dir", type=Path, required=True)

    status_p = sub.add_parser("status")
    status_p.add_argument("--state", type=Path, required=True)

    shadow_p = sub.add_parser("shadow-run")
    shadow_p.add_argument("--mode", default="ping_scan")
    shadow_p.add_argument("--fixture", type=Path, default=FIXTURE)
    shadow_p.add_argument("--output", type=Path, required=True)
    shadow_p.add_argument("--channel")
    shadow_p.add_argument("--thread-ts")

    parity_p = sub.add_parser("parity-check")
    parity_p.add_argument("--decisions", type=Path, required=True)
    parity_p.add_argument("--posts", type=Path, required=True)
    parity_p.add_argument("--start", required=True)
    parity_p.add_argument("--end", required=True)

    models_p = sub.add_parser("models", help="List source-configurable BYOK role choices without loading credentials")
    models_p.add_argument("--role", choices=("mmsecretary", "mmmeta"), required=True)

    doctor_p = sub.add_parser("doctor")
    doctor_p.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            payload = _install(args)
        elif args.command == "uninstall":
            payload = _uninstall(args.state, args.systemd_user_dir)
        elif args.command == "status":
            payload = _status(args.state)
        elif args.command == "shadow-run":
            payload = routine_tick(
                mode=args.mode,
                fixture=args.fixture,
                output=args.output,
                channel=args.channel,
                thread_ts=args.thread_ts,
            )
            payload = {
                "count": payload["count"],
                "admitted": payload["admitted"],
                "slack_methods": payload["slack_methods"],
                "output": payload["output"],
                "would_post": False,
            }
        elif args.command == "parity-check":
            payload = _parity(args.decisions, args.posts, args.start, args.end)
        elif args.command == "models":
            payload = _models(args.role)
        elif args.command == "doctor":
            report = doctor()
            if args.json:
                print(json.dumps(report, sort_keys=True))
            else:
                print(format_doctor(report), end="")
            return 0 if report["status"] == "READY" else 2
        else:
            raise RuntimeRefusal("COMMAND_INVALID")
    except RuntimeRefusal as exc:
        print(exc.code, file=sys.stderr)
        return 2
    except (OSError, RuntimeError, ValueError) as exc:
        code = getattr(exc, "code", None) or "HARNESS_FAILED"
        print(code if code != "HARNESS_FAILED" else "HARNESS_FAILED", file=sys.stderr)
        return 2
    print(json.dumps(payload, sort_keys=True))
    return 0


def _install(args: argparse.Namespace) -> dict:
    # Import on invocation: read-only shadow jobs must not depend on PyYAML.
    from integrations.hermes_harness.native_byok import render_disarmed_native_byok
    selected_provider = _install_selection(args)
    profile_path = args.state.parent / f"{args.role}.hermes-profile.yaml"
    write_composed_profile(
        args.role,
        state_dir=args.state,
        secrets_file=args.secrets_file,
        dest=profile_path,
        installed_native_only=True,
        native_provider_id=selected_provider,
    )
    payload = runtime_install(
        profile_path=profile_path,
        state_dir=args.state,
        systemd_user_dir=args.systemd_user_dir,
        secrets_file=args.secrets_file,
        hermes_bin=args.hermes_bin,
        upstream_source=args.upstream_source,
        fetch=bool(args.fetch),
        hermes_config_renderer=render_disarmed_native_byok,
    )
    home = args.state / "current" / "hermes-home"
    overlays = render_overlays()
    from integrations.hermes_models.profile_config import render_profile
    overlays[args.role] = render_profile(args.role, native_provider_id=selected_provider)
    _write(home / "provider-overlay.yaml", overlays[args.role])
    _write(home / "vision-overlay.yaml", overlays["vision"])
    payload["overlay_chain"] = list(overlay_chain(args.role))
    payload["vision_chain"] = list(overlay_chain("vision"))
    payload["extensions_registered"] = False
    payload["unbound_extension_names"] = "NOT_INSTALLED"
    payload["native_steward_mcp"] = "CONFIGURED_DISABLED"
    payload["native_steward_connected"] = False
    payload["native_model_profile"] = "CONFIGURED_KEY_NAMES_ONLY"
    payload["provider_called"] = False
    payload["native_model_selection"] = _model_selection(load_profile(args.state / "current" / "profile.yaml"))
    return payload


def _install_selection(args: argparse.Namespace) -> str | None:
    """Preserve an installed role choice on upgrade unless explicitly changed."""
    from integrations.hermes_models.contract import native_provider
    selected = getattr(args, "model_provider", None)
    if (args.state / "install-manifest.json").is_file():
        previous_path = args.state / "current" / "profile.yaml"
        if not previous_path.is_file():
            raise RuntimeRefusal("NATIVE_UPGRADE_PROFILE_MISSING")
        previous = load_profile(previous_path)
        if previous.role != args.role:
            raise RuntimeRefusal("NATIVE_UPGRADE_ROLE_MISMATCH")
        if selected is None:
            selected = previous.native_provider_id
    try:
        native_provider(args.role, selected)
    except (ValueError, KeyError):
        raise RuntimeRefusal("NATIVE_MODEL_SELECTION_UNQUALIFIED") from None
    return selected


def _model_selection(profile) -> dict:
    from integrations.hermes_models.contract import native_provider
    try:
        spec = native_provider(profile.role, profile.native_provider_id)
    except (ValueError, KeyError):
        raise RuntimeRefusal("NATIVE_MODEL_SELECTION_UNQUALIFIED") from None
    return {
        "provider_id": spec.provider_id,
        "native_provider": spec.hermes_name,
        "requested_model": spec.served_model,
        "served_model_verified": False,
        "credential_env": spec.credential_env,
        "credential_file_env": spec.credential_file_env,
        "automatic_fallback": False,
        "provider_called": False,
    }


def _models(role: str) -> dict:
    from integrations.hermes_models.contract import PROFILE_PRIMARY, native_provider_choices
    return {
        "role": role,
        "default_provider_id": PROFILE_PRIMARY[role],
        "choices": [{
            "provider_id": spec.provider_id,
            "native_provider": spec.hermes_name,
            "requested_model": spec.served_model,
            "credential_file_env": spec.credential_file_env,
        } for spec in native_provider_choices(role)],
        "selection_is_admission": False,
        "automatic_fallback": False,
        "provider_called": False,
        "credentials_read": False,
    }


def _uninstall(state: Path, unit_dir: Path) -> dict:
    role = _role_from_manifest(state)
    payload = runtime_uninstall(state_dir=state, systemd_user_dir=unit_dir)
    if role:
        leftover = state.parent / f"{role}.hermes-profile.yaml"
        if leftover.is_file() and not leftover.is_symlink():
            leftover.unlink()
    return payload


def _status(state: Path) -> dict:
    manifest_path = state / "install-manifest.json"
    if not manifest_path.is_file():
        return {"schema": "mastermind.hermes_harness.status.v1", "status": "ABSENT", "secrets_recorded": False}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    profile_path = state / "current" / "profile.yaml"
    allowlist: list[str] = []
    role = ""
    native_selection = None
    if profile_path.is_file():
        profile = load_profile(profile_path)
        allowlist = sorted(profile.tool_allowlist)
        role = profile.role
        native_selection = _model_selection(profile)
    overlay = state / "current" / "hermes-home" / "provider-overlay.yaml"
    chain: list[str] = []
    if role in {"mmsecretary", "mmmeta"}:
        chain = list(overlay_chain(role))
    return {
        "schema": "mastermind.hermes_harness.status.v1",
        "status": "INSTALLED",
        "role": role,
        "release": manifest.get("current_release"),
        "sha": manifest.get("sha"),
        "allowlist": allowlist,
        "overlay_present": overlay.is_file(),
        "overlay_chain": chain,
        "native_model_selection": native_selection,
        "provider_called": False,
        "vision_chain": list(overlay_chain("vision")),
        "secrets_recorded": False,
    }


def _parity(decisions_path: Path, posts_path: Path, start: str, end: str) -> dict:
    root = Path(__file__).resolve().parents[1] / "hermes_secretary"
    text = str(root)
    if text not in sys.path:
        sys.path.insert(0, text)
    import parity

    decisions = parity.load_decisions(decisions_path)
    posts = json.loads(posts_path.read_text(encoding="utf-8"))
    if not isinstance(posts, list):
        raise ValueError("POSTS_NOT_A_LIST")
    report = parity.compare(decisions=decisions, posts=posts, start_ts=start, end_ts=end)
    return {
        "schema": "mastermind.hermes_harness.parity.v1",
        "matched": list(report.matched),
        "shadow_only": list(report.shadow_only),
        "secretary_only": list(report.secretary_only),
        "mismatched_kind": list(report.mismatched_kind),
        "withheld": list(report.withheld),
    }


def _role_from_manifest(state: Path) -> str:
    path = state / "install-manifest.json"
    if not path.is_file():
        return ""
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    service = manifest.get("service_name")
    if not isinstance(service, str) or not service.startswith("hermes-runtime-"):
        return ""
    return service.removeprefix("hermes-runtime-")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o600)


if __name__ == "__main__":
    raise SystemExit(main())
