"""Operator-guided local setup for MAS-115 managed-browser proof.

This utility removes the need to transcribe managed-browser folder IDs or edit
JSON by hand. It discovers only local profile identities and reduced running
flags, then matches the profile ID copied from the vendor's own profile list. Private
profile IDs and ChatGPT URLs are entered with terminal echo disabled and are
written only to the existing local provision/navigation files.

No vendor credential is accepted by this Python process. ``credential``
replaces the process with macOS ``security ... -w`` where ``-w`` is the last
argument, causing Keychain itself to prompt securely.  The value therefore
never appears in Python memory, argv, environment, stdout, a shell variable,
or a repository file.

The utility never starts or stops a browser profile. Seat lifecycle is not
touched at all; the accepted canary helper later owns only the already-stopped
disposable profile through the documented vendor contract.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Direct operator invocation sets ``sys.path[0]`` to ``scripts/`` rather than
# the repository root.  Bootstrap the root before importing Mastermind
# packages so the documented ``python3 scripts/mas115_setup.py ...`` commands
# work without a hidden PYTHONPATH requirement.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_REPO_ROOT))

from control_plane import surface_bindings as sb
from integrations.chairman_surfaces import chatgpt
from integrations.chairman_surfaces import nonseat_canary as canary
from integrations.chairman_surfaces import nonseat_canary_vendors as vendors


WORK_REF = "WS:CHAIRMAN-CONTROL-ROOM"
SEAT_REFS = ("chatgpt1", "chatgpt2", "chatgpt3")
_CONFIRM_ENROLL = "ENROLL THREE CHAIRMAN SEATS"
_MAX_PRIVATE_URL_BYTES = 8 * 1024


class SetupRefusal(ValueError):
    """Fixed, operator-readable setup refusal."""


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _identity(row: dict) -> tuple[str, str | None, str]:
    manager = row.get("env_manager")
    profile_id = row.get("profile_id")
    folder_id = row.get("folder_id") if manager == "multilogin" else None
    if manager not in sb.ENV_MANAGERS or not isinstance(profile_id, str):
        raise SetupRefusal("the selected managed-browser environment is malformed")
    return manager, folder_id, profile_id


def _candidate_rows(census: dict) -> list[dict]:
    """Normalize the existing read-only census into one closed candidate list."""
    rows: list[dict] = []
    for manager in sb.ENV_MANAGERS:
        for raw in census.get(manager) or []:
            if not isinstance(raw, dict):
                continue
            row = {
                "env_manager": manager,
                "profile_id": raw.get("profile_id"),
                "running": raw.get("running") is True,
            }
            if manager == "multilogin":
                row["workspace_id"] = raw.get("workspace_id")
                row["folder_id"] = raw.get("folder_id")
            try:
                manager_value, folder_id, profile_id = _identity(row)
            except SetupRefusal:
                continue
            valid = (
                bool(sb.UUID_RE.fullmatch(profile_id))
                and isinstance(folder_id, str)
                and bool(sb.UUID_RE.fullmatch(folder_id))
            ) if manager_value == "multilogin" else bool(sb.GOLOGIN_PROFILE_ID_RE.fullmatch(profile_id))
            if valid:
                rows.append(row)
    rows.sort(key=lambda item: _identity(item))
    return rows


def _locator(row: dict, url: str) -> dict:
    manager, folder_id, profile_id = _identity(row)
    locator = {"env_manager": manager, "profile_id": profile_id, "url": url}
    if manager == "multilogin":
        locator["folder_id"] = folder_id
    return locator


def build_enrollment_document(existing: dict | None, selections: dict[str, tuple[dict, str]], *, observed_at: str) -> dict:
    """Replace the three CCR initial destinations while preserving other chats."""
    if set(selections) != set(SEAT_REFS):
        raise SetupRefusal("all three Chairman ChatGPT seats must be selected in one enrollment")
    identities = [_identity(selections[seat][0]) for seat in SEAT_REFS]
    if len(set(identities)) != len(SEAT_REFS):
        raise SetupRefusal("one managed-browser environment cannot be assigned to two Chairman seats")

    base = existing if existing is not None else {"schema": sb.SCHEMA, "bindings": []}
    problems = sb.validate_bindings_document(base)
    if problems:
        raise SetupRefusal("the existing surface-bindings file is invalid; no enrollment was written")
    selected_identities = {
        seat_ref: _identity(selections[seat_ref][0]) for seat_ref in SEAT_REFS
    }
    preserved = []
    for binding in base.get("bindings", []):
        is_named_chatgpt_seat = (
            isinstance(binding, dict)
            and binding.get("provider") == "chatgpt"
            and binding.get("seat_ref") in SEAT_REFS
        )
        is_ccr_initial_destination = (
            is_named_chatgpt_seat
            and binding.get("work_ref") == WORK_REF
            and binding.get("role") == "ceo"
        )
        if is_ccr_initial_destination:
            continue
        if is_named_chatgpt_seat:
            seat_ref = binding["seat_ref"]
            locator = binding.get("locator")
            try:
                existing_identity = _identity(locator)
            except SetupRefusal as exc:
                raise SetupRefusal(
                    "an existing work-specific ChatGPT binding has a malformed managed-environment identity"
                ) from exc
            if existing_identity != selected_identities[seat_ref]:
                raise SetupRefusal(
                    "an existing work-specific chat uses a different environment for this seat; "
                    "reconcile or unbind it before changing the seat"
                )
        preserved.append(binding)
    enrolled = []
    for seat_ref in SEAT_REFS:
        row, url = selections[seat_ref]
        enrolled.append(sb.new_binding(
            work_ref=WORK_REF,
            role="ceo",
            provider="chatgpt",
            locator_kind="chatgpt_managed_env",
            locator=_locator(row, url),
            observed_at=observed_at,
            seat_ref=seat_ref,
        ))
    result = {"schema": sb.SCHEMA, "bindings": preserved + enrolled}
    problems = sb.validate_bindings_document(result)
    if problems:
        raise SetupRefusal("the proposed enrollment failed the canonical binding schema; nothing was written")
    if sb.find_conflicts(result):
        raise SetupRefusal("the proposed enrollment would create an ambiguous surface binding; nothing was written")
    return result


def _detect_multilogin_browser_type(row: dict, *, mlx_profiles_root: str | None = None) -> str | None:
    """Infer only from browser-core-specific on-disk shape; never read profile content."""
    if row.get("env_manager") != "multilogin":
        return None
    root = Path(mlx_profiles_root or chatgpt.MLX_PROFILES_ROOT).expanduser()
    path = root / str(row.get("workspace_id")) / str(row.get("folder_id")) / str(row.get("profile_id"))
    try:
        mimic = (path / "Default").is_dir() or (path / "Local State").is_file()
        stealthfox = (path / "prefs.js").is_file() or (path / "places.sqlite").is_file()
    except OSError:
        return None
    if mimic == stealthfox:
        return None
    return "mimic" if mimic else "stealthfox"


def build_provision(row: dict, *, browser_type: str | None) -> dict:
    manager, folder_id, profile_id = _identity(row)
    if row.get("running") is True:
        raise SetupRefusal("the disposable profile must be stopped before it can be provisioned")
    doc = {
        "schema": canary.PROVISION_SCHEMA,
        "vendor": manager,
        "profile_id": profile_id,
        "benign_origin": "http://127.0.0.1:7777",
        "disposable_ack": canary.REQUIRED_ACK,
    }
    if manager == "multilogin":
        if browser_type not in ("mimic", "stealthfox"):
            raise SetupRefusal("the disposable Multilogin browser core must be positively identified")
        doc["folder_id"] = folder_id
        doc["browser_type"] = browser_type
    return doc


def assert_current_nonseat(bound_doc: dict, row: dict, *, now: datetime) -> None:
    """Require the canonical fresh three-seat census before any provision write."""
    _manager, _folder_id, profile_id = _identity(row)
    census = canary._current_chairman_profile_census(  # noqa: SLF001 — reuse the canary's load-bearing gate
        bound_doc, now=now, candidate_profile_id=profile_id,
    )
    if census == "collision":
        raise SetupRefusal("the selected disposable profile collides with a Chairman seat")
    if census != "clear":
        raise SetupRefusal(
            "all three current Chairman seat bindings are required before a disposable profile can be prepared"
        )


def _atomic_private_json(doc: dict, path: str | Path) -> None:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    content = (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode("utf-8")
    tmp = tempfile.NamedTemporaryFile(
        dir=os.fspath(target.parent), prefix=f".{target.name}.", suffix=".tmp", delete=False,
    )
    try:
        os.fchmod(tmp.fileno(), 0o600)
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
    finally:
        tmp.close()
    try:
        os.replace(tmp.name, target)
        os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


def credential_setup_argv(vendor: str) -> list[str]:
    if vendor != "multilogin":
        raise SetupRefusal("GoLogin live lifecycle remains unsupported; no GoLogin credential will be stored")
    # Per `security help add-generic-password`, a final bare -w prompts rather
    # than placing the password in argv. Do not append anything after it.
    return [
        vendors._SECURITY_BIN, "add-generic-password", "-U",
        "-a", vendors._KEYCHAIN_ACCOUNT, "-s", vendors._KEYCHAIN_SERVICE, "-w",
    ]


def _private_url(prompt: str) -> str:
    value = getpass.getpass(prompt).strip()
    if not value or len(value.encode("utf-8")) > _MAX_PRIVATE_URL_BYTES:
        raise SetupRefusal("the private conversation URL is missing or too large")
    problem = sb._check_chatgpt_url(value)  # noqa: SLF001 — reuse the canonical exact-chat validator
    if problem:
        raise SetupRefusal(f"the private ChatGPT URL {problem}")
    return value


def _copied_profile(prompt: str, rows: list[dict]) -> dict:
    copied = getpass.getpass(prompt).strip()
    if not copied or len(copied.encode("utf-8")) > 256:
        raise SetupRefusal("the copied profile ID is missing or too large")
    matches = [row for row in rows if str(row.get("profile_id", "")).lower() == copied.lower()]
    if len(matches) != 1:
        raise SetupRefusal("the copied profile ID did not match exactly one local managed-browser environment")
    return matches[0]


def enroll_interactive() -> int:
    print("Seat enrollment does not start, stop, or inspect any profile content.")
    print("In the GoLogin/Multilogin profile list, use Copy profile ID for each Chairman seat.")
    print("Sol is bootstrapped by the ChatGPT account plus the MastermindX Project context, not by one primary chat.")
    print("Choose one exact existing conversation as each seat's initial navigation destination.")
    print("Normal-chat and Project-chat URLs are accepted; the Project overview is not an exact destination.")
    candidates = _candidate_rows(chatgpt.list_local_environments())
    selections: dict[str, tuple[dict, str]] = {}
    used: set[tuple[str, str | None, str]] = set()
    for index, seat_ref in enumerate(SEAT_REFS, start=1):
        selected = _copied_profile(
            f"\nPaste the copied profile ID for ChatGPT Seat {index} (input is hidden): ",
            candidates,
        )
        if _identity(selected) in used:
            raise SetupRefusal("one managed-browser environment cannot be assigned to two Chairman seats")
        url = _private_url(
            f"Copy one exact normal-chat or Project-chat URL for ChatGPT Seat {index} "
            "(not the Project overview), "
            "paste it here, then press Return: "
        )
        selections[seat_ref] = (selected, url)
        used.add(_identity(selected))
        print(f"Seat {index} captured securely.")

    if input(f"\nType {_CONFIRM_ENROLL!r} to write all three bindings atomically: ").strip() != _CONFIRM_ENROLL:
        raise SetupRefusal("enrollment confirmation did not match; nothing was written")
    existing, problems = sb.load_bindings()
    if problems:
        raise SetupRefusal("the existing surface-bindings file has problems; nothing was written")
    doc = build_enrollment_document(existing, selections, observed_at=_utc_now_z())
    sb.save_bindings(doc)
    print("All three Chairman ChatGPT seat navigation destinations are enrolled.")
    print("They do not define Sol identity; other chats remain independently bindable.")
    print("No profile was started or stopped by this tool.")
    return 0


def provision_interactive() -> int:
    bound_doc, problems = sb.load_bindings()
    if problems or bound_doc is None:
        raise SetupRefusal("enroll all three Chairman ChatGPT seats before preparing a disposable profile")
    print("In the vendor profile list, use Copy profile ID on the disposable non-Chairman profile.")
    candidates = _candidate_rows(chatgpt.list_local_environments())
    refreshed = _copied_profile("Paste the disposable profile ID (input is hidden): ", candidates)
    assert_current_nonseat(bound_doc, refreshed, now=datetime.now(timezone.utc))
    if refreshed.get("running") is True:
        raise SetupRefusal("the selected disposable profile is running; stop it cleanly before provisioning")

    browser_type = _detect_multilogin_browser_type(refreshed)
    if refreshed.get("env_manager") == "multilogin" and browser_type is None:
        entered = input("Browser core could not be inferred. Type mimic or stealthfox: ").strip().lower()
        browser_type = entered
    provision = build_provision(refreshed, browser_type=browser_type)
    if input(f"Type {canary.REQUIRED_ACK!r} to attest this is disposable and not a Chairman seat: ").strip() != canary.REQUIRED_ACK:
        raise SetupRefusal("disposable acknowledgement did not match; nothing was written")
    _atomic_private_json(provision, canary.DEFAULT_PROVISION_PATH)

    loaded, code = canary.load_provision(canary.DEFAULT_PROVISION_PATH)
    if loaded is None:
        raise SetupRefusal(f"the written provision failed its safety preflight ({code}); it was not accepted")
    print("Disposable profile provisioned. The canary has not been run.")
    return 0


def status() -> int:
    census = _candidate_rows(chatgpt.list_local_environments())
    bindings, problems = sb.load_bindings()
    seats = set()
    if bindings is not None and not problems:
        seats = {
            row.get("seat_ref") for row in bindings.get("bindings", [])
            if isinstance(row, dict) and row.get("provider") == "chatgpt"
        } & set(SEAT_REFS)
    provision, code = canary.load_provision(canary.DEFAULT_PROVISION_PATH)
    print(json.dumps({
        "local_environment_counts": {
            manager: {
                "total": sum(row["env_manager"] == manager for row in census),
                "running": sum(row["env_manager"] == manager and row["running"] for row in census),
            }
            for manager in sb.ENV_MANAGERS
        },
        "chairman_seats_enrolled": len(seats),
        "bindings_healthy": not problems,
        "disposable_provision_ready": provision is not None,
        "disposable_provision_code": None if provision is not None else code,
    }, indent=2, sort_keys=True))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="mas115_setup")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="show only sanitized local readiness counts")
    sub.add_parser("enroll-seats", help="securely enroll ChatGPT Seat 1/2/3")
    sub.add_parser("prepare-disposable", help="prepare one stopped non-Chairman profile")
    credential_parser = sub.add_parser("credential", help="open the native Keychain password prompt")
    credential_parser.add_argument("--vendor", default="multilogin", choices=("multilogin", "gologin"))
    run_parser = sub.add_parser("run-canary", help="run the accepted disposable canary")
    run_parser.add_argument("--vendor", default="multilogin", choices=("multilogin", "gologin"))
    args = parser.parse_args(argv)

    try:
        if args.command == "status":
            return status()
        if args.command == "enroll-seats":
            return enroll_interactive()
        if args.command == "prepare-disposable":
            return provision_interactive()
        if args.command == "credential":
            argv = credential_setup_argv(args.vendor)
            os.execve(argv[0], argv, {})
        if args.command == "run-canary":
            return vendors.main([
                "--vendor", args.vendor,
                "--provision-path", str(Path(canary.DEFAULT_PROVISION_PATH).expanduser()),
            ])
    except SetupRefusal as refusal:
        print(f"REFUSED: {refusal}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
