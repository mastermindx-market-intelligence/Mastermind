"""Operator-guided local setup for MAS-115 managed-browser proof.

This utility removes the need to transcribe managed-browser folder IDs or edit
JSON by hand. It discovers only local profile identities and reduced running
flags, then matches the profile ID copied from the vendor's own profile list. Private
profile IDs and ChatGPT URLs are entered with terminal echo disabled and are
written only to the existing local provision/navigation files.

No vendor credential is accepted by this coordinator process. ``credential``
replaces it with the dedicated MAS-115 secret-owning helper, which uses an
echo-disabled terminal prompt and macOS Security.framework to store long
tokens without putting the value in argv, environment, stdout, a temporary
file, a shell variable, or a repository file.

The utility never starts or stops a browser profile. Seat lifecycle is not
touched at all; the accepted canary helper later owns only the already-stopped
disposable profile through the documented vendor contract.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
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
from integrations.chairman_surfaces import mas115_multilogin_port_policy as port_policy


WORK_REF = "WS:CHAIRMAN-CONTROL-ROOM"
SEAT_REFS = ("chatgpt1", "chatgpt2", "chatgpt3")
_CONFIRM_ENROLL = "ENROLL THREE CHAIRMAN SEATS"
_CONFIRM_BOOTSTRAP_PEER = "BOOTSTRAP THE EXISTING DISPOSABLE PEER LIFECYCLE"
_CONFIRM_CREATE_PEER = "CREATE ONE DISPOSABLE PEER PROFILE"
_CONFIRM_ROLLBACK_PEER = "REMOVE THE OPERATION-CREATED PEER PROFILE"
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
        "origin_policy": port_policy.ORIGIN_POLICY,
        "disposable_ack": canary.REQUIRED_ACK,
    }
    if manager == "multilogin":
        if browser_type not in ("mimic", "stealthfox"):
            raise SetupRefusal("the disposable Multilogin browser core must be positively identified")
        doc["folder_id"] = folder_id
        doc["browser_type"] = browser_type
    return doc


def assert_current_nonseat(
    bound_doc: dict, row: dict, *, now: datetime,
    current_environment_snapshot=None,
) -> None:
    """Require the canonical fresh three-seat census before any provision write."""
    manager, folder_id, profile_id = _identity(row)
    census = canary._current_chairman_profile_census(  # noqa: SLF001 — reuse the canary's load-bearing gate
        bound_doc,
        now=now,
        candidate_profile_id=profile_id,
        candidate_vendor=manager,
        candidate_folder_id=folder_id,
        current_environment_snapshot=current_environment_snapshot,
    )
    if census == "collision":
        raise SetupRefusal("the selected disposable profile collides with a Chairman seat")
    if census != "clear":
        raise SetupRefusal(
            "all three current Chairman seat bindings are required before a disposable profile can be prepared"
        )


#: Single implementation lives in vendors.py (REALM1-C1 spec §3.10); this
#: name is kept for every existing caller/test in this module.
_atomic_private_json = vendors.atomic_private_json


def _initialize_peer_lifecycle_for_anchor(
    provision: dict, *, state_path=vendors.PEER_INTENT_PATH,
    peer_provision_path=vendors.PEER_PROVISION_PATH,
) -> None:
    """Pre-provision the inert peer lifecycle inode during trusted setup."""
    folder_id = provision.get("folder_id")
    anchor_profile_id = provision.get("profile_id")
    if not isinstance(folder_id, str) or not isinstance(anchor_profile_id, str):
        raise SetupRefusal("the disposable anchor cannot initialize peer lifecycle state")
    outcome = vendors.initialize_peer_lifecycle_state(
        state_path,
        folder_id=folder_id,
        anchor_profile_id=anchor_profile_id,
        peer_name=vendors.peer_profile_name(folder_id, anchor_profile_id),
        peer_provision_path=peer_provision_path,
    )
    if outcome not in (vendors.CREATED_THIS_CALL, vendors.EXISTING_EXACT):
        raise SetupRefusal("the peer lifecycle genesis is unavailable or already consumed")


def _exact_initialized_peer_lifecycle(
    provision: dict, *, state_path=vendors.PEER_INTENT_PATH,
    peer_provision_path=vendors.PEER_PROVISION_PATH,
):
    """Read one exact inert genesis without creating or re-arming it."""
    folder_id = provision.get("folder_id")
    anchor_profile_id = provision.get("profile_id")
    if not isinstance(folder_id, str) or not isinstance(anchor_profile_id, str):
        raise SetupRefusal("the disposable anchor cannot bind peer lifecycle state")
    try:
        state, peer_provision = vendors._preflight_peer_paths(  # noqa: SLF001
            operation="create-peer-profile",
            state_path=state_path,
            provision_path=peer_provision_path,
        )
    except vendors._PeerStateRefusal:  # noqa: SLF001
        raise SetupRefusal("the peer lifecycle genesis is unavailable or already consumed") from None
    if (
        peer_provision is not None
        or state.document.get("phase") != vendors.PEER_PHASE_INITIALIZED
        or not vendors._state_matches_authority(  # noqa: SLF001
            state,
            folder_id=folder_id,
            anchor_profile_id=anchor_profile_id,
            peer_name=vendors.peer_profile_name(folder_id, anchor_profile_id),
            peer_provision_path=peer_provision_path,
        )
    ):
        raise SetupRefusal("the peer lifecycle genesis is unavailable or already consumed")
    return state


def _prepare_anchor_with_peer_lifecycle(
    provision: dict, *, anchor_path=canary.DEFAULT_PROVISION_PATH,
    state_path=vendors.PEER_INTENT_PATH,
    peer_provision_path=vendors.PEER_PROVISION_PATH,
) -> str:
    """One-time setup of the anchor and inert peer lifecycle genesis.

    Runtime create never calls this helper.  If an anchor already exists, a
    missing lifecycle is indistinguishable from deletion after dispatch and is
    therefore terminally refused before the anchor inode can be replaced.
    """
    try:
        existing_anchor = vendors._optional_private_json_snapshot(anchor_path)  # noqa: SLF001
    except vendors._PeerStateRefusal:  # noqa: SLF001
        raise SetupRefusal("the disposable anchor path is not a private exact file") from None

    if existing_anchor is not None:
        if existing_anchor.document != provision:
            raise SetupRefusal("an existing disposable anchor cannot be replaced by prepare-disposable")
        state = _exact_initialized_peer_lifecycle(
            provision,
            state_path=state_path,
            peer_provision_path=peer_provision_path,
        )
        try:
            current_anchor = vendors._optional_private_json_snapshot(anchor_path)  # noqa: SLF001
        except vendors._PeerStateRefusal:  # noqa: SLF001
            current_anchor = None
        current_state = _exact_initialized_peer_lifecycle(
            provision,
            state_path=state_path,
            peer_provision_path=peer_provision_path,
        )
        if (
            current_anchor is None
            or not vendors._same_snapshot(current_anchor, existing_anchor)  # noqa: SLF001
            or not vendors._same_snapshot(current_state, state)  # noqa: SLF001
        ):
            raise SetupRefusal("the disposable anchor or peer lifecycle changed during setup")
        return vendors.EXISTING_EXACT

    # A missing anchor is the only ordinary setup state allowed to mint the
    # genesis.  A prior crash may already have left the exact inert genesis;
    # accepting it is safe because no runtime effect can precede a valid anchor.
    _initialize_peer_lifecycle_for_anchor(
        provision,
        state_path=state_path,
        peer_provision_path=peer_provision_path,
    )
    state = _exact_initialized_peer_lifecycle(
        provision,
        state_path=state_path,
        peer_provision_path=peer_provision_path,
    )
    outcome, anchor_snapshot = vendors._exclusive_private_json(  # noqa: SLF001
        anchor_path, provision,
    )
    if outcome not in (vendors.CREATED_THIS_CALL, vendors.EXISTING_EXACT):
        raise SetupRefusal("the disposable anchor appeared or changed during setup")
    try:
        current_anchor = vendors._optional_private_json_snapshot(anchor_path)  # noqa: SLF001
    except vendors._PeerStateRefusal:  # noqa: SLF001
        current_anchor = None
    current_state = _exact_initialized_peer_lifecycle(
        provision,
        state_path=state_path,
        peer_provision_path=peer_provision_path,
    )
    if (
        anchor_snapshot is None
        or current_anchor is None
        or not vendors._same_snapshot(current_anchor, anchor_snapshot)  # noqa: SLF001
        or not vendors._same_snapshot(current_state, state)  # noqa: SLF001
    ):
        raise SetupRefusal("the disposable anchor or peer lifecycle changed during setup")
    return outcome


def _migrate_legacy_provision(
    path=canary.DEFAULT_PROVISION_PATH, *, bindings_loader=None, now=None,
    peer_intent_path=None, peer_provision_path=None,
    current_environment_snapshot=None,
):
    """Atomically migrate only the exact validated historical provision."""

    migrated, code = canary.load_legacy_provision_for_migration(
        path,
        bindings_loader=bindings_loader,
        now=now,
        current_environment_snapshot=current_environment_snapshot,
    )
    if migrated is None:
        return None, code
    should_initialize_peer = (
        peer_intent_path is not None
        or Path(path).expanduser() == Path(canary.DEFAULT_PROVISION_PATH).expanduser()
    )
    if should_initialize_peer:
        # Exact legacy migration is the sole exception to the ordinary rule
        # forbidding genesis creation beside an existing anchor.  Seed before
        # replacement so a consumed/mismatched lifecycle refuses with the
        # historical anchor inode and bytes untouched.
        _initialize_peer_lifecycle_for_anchor(
            migrated,
            state_path=peer_intent_path or vendors.PEER_INTENT_PATH,
            peer_provision_path=peer_provision_path or vendors.PEER_PROVISION_PATH,
        )
    _atomic_private_json(migrated, path)
    loaded, code = canary.load_provision(
        path,
        bindings_loader=bindings_loader,
        now=now,
        current_environment_snapshot=current_environment_snapshot,
    )
    if loaded is not None and should_initialize_peer:
        _exact_initialized_peer_lifecycle(
            loaded,
            state_path=peer_intent_path or vendors.PEER_INTENT_PATH,
            peer_provision_path=peer_provision_path or vendors.PEER_PROVISION_PATH,
        )
    return (loaded, None) if loaded is not None else (None, code)


def credential_setup_argv(vendor: str) -> list[str]:
    if vendor != "multilogin":
        raise SetupRefusal("GoLogin live lifecycle remains unsupported; no GoLogin credential will be stored")
    helper = _REPO_ROOT / "scripts" / "mas115_keychain_store.py"
    return [sys.executable, os.fspath(helper)]


def _acquire_current_environment_snapshot():
    """Acquire and immediately seal one strict local environment observation."""

    try:
        raw = chatgpt.list_local_environments()
        snapshot = canary._seal_current_environment_snapshot(raw)  # noqa: SLF001
    except Exception:  # noqa: BLE001 — setup exposes one fixed refusal
        raise SetupRefusal(
            "the current local managed-browser census is unavailable"
        ) from None
    if snapshot is None:
        raise SetupRefusal("the current local managed-browser census is unavailable")
    return snapshot


def _load_current_provision(*, current_environment_snapshot=None):
    """Load the provision with the live UTC reference time required by its census gate."""
    kwargs = {"now": datetime.now(timezone.utc)}
    if current_environment_snapshot is not None:
        kwargs["current_environment_snapshot"] = current_environment_snapshot
    return canary.load_provision(canary.DEFAULT_PROVISION_PATH, **kwargs)


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
    current_environment_snapshot = _acquire_current_environment_snapshot()
    candidates = [dict(row) for row in current_environment_snapshot.rows]
    refreshed = _copied_profile("Paste the disposable profile ID (input is hidden): ", candidates)
    assert_current_nonseat(
        bound_doc,
        refreshed,
        now=datetime.now(timezone.utc),
        current_environment_snapshot=current_environment_snapshot,
    )
    if refreshed.get("running") is True:
        raise SetupRefusal("the selected disposable profile is running; stop it cleanly before provisioning")

    browser_type = _detect_multilogin_browser_type(refreshed)
    if refreshed.get("env_manager") == "multilogin" and browser_type is None:
        entered = input("Browser core could not be inferred. Type mimic or stealthfox: ").strip().lower()
        browser_type = entered
    provision = build_provision(refreshed, browser_type=browser_type)
    if input(f"Type {canary.REQUIRED_ACK!r} to attest this is disposable and not a Chairman seat: ").strip() != canary.REQUIRED_ACK:
        raise SetupRefusal("disposable acknowledgement did not match; nothing was written")
    _prepare_anchor_with_peer_lifecycle(provision)

    loaded, code = _load_current_provision(
        current_environment_snapshot=current_environment_snapshot,
    )
    if loaded is None:
        raise SetupRefusal(f"the written provision failed its safety preflight ({code}); it was not accepted")
    print("Disposable profile provisioned. The canary has not been run.")
    return 0


def _matching_local_row(bound_doc: dict) -> dict:
    """Re-identify the anchor provision's exact profile in the fresh local
    census, then re-run the three-seat exclusion against it. Raises
    :class:`SetupRefusal` on any missing/ambiguous/colliding state."""
    current_environment_snapshot = _acquire_current_environment_snapshot()
    loaded, code = _load_current_provision(
        current_environment_snapshot=current_environment_snapshot,
    )
    if loaded is None:
        raise SetupRefusal(f"the disposable profile provision is unavailable ({code}); prepare it first")
    matches = [
        row for row in current_environment_snapshot.rows
        if row["env_manager"] == "multilogin"
        and row["profile_id"] == loaded.get("profile_id")
        and row["folder_id"] == loaded.get("folder_id")
    ]
    if len(matches) != 1:
        raise SetupRefusal("the disposable profile could not be re-identified in the local census")
    if matches[0]["running"] is True:
        raise SetupRefusal("the disposable profile is running; stop it cleanly before continuing")
    row = dict(matches[0])
    assert_current_nonseat(
        bound_doc,
        row,
        now=datetime.now(timezone.utc),
        current_environment_snapshot=current_environment_snapshot,
    )
    return row


def create_peer_interactive() -> int:
    """Create the one missing stopped disposable Multilogin peer profile.

    This coordinator never reads the credential, never constructs vendor
    HTTP, and never sees a raw vendor response — it only forwards the exit
    code and lets ``vendors.main`` print its own receipt.
    """
    if not vendors.coordinator_peer_paths_safe("create-peer-profile"):
        raise SetupRefusal("peer lifecycle paths are unsafe or inconsistent")
    bound_doc, problems = sb.load_bindings()
    if problems or bound_doc is None:
        raise SetupRefusal("enroll all three Chairman ChatGPT seats before preparing a disposable peer profile")
    _matching_local_row(bound_doc)
    if input(f"Type {_CONFIRM_CREATE_PEER!r} to create one disposable peer profile: ").strip() != _CONFIRM_CREATE_PEER:
        raise SetupRefusal("peer-create confirmation did not match; nothing was dispatched")
    return vendors.run_coordinator_peer_create([
        "--vendor", "multilogin",
        "--provision-path", str(Path(canary.DEFAULT_PROVISION_PATH).expanduser()),
    ])


def bootstrap_peer_interactive() -> int:
    """Bootstrap lifecycle state for the exact historical stopped anchor.

    This coordinator performs the current binding/census ceremony, then passes
    one opaque in-process capability to the fixed-coordinate local state seam.
    It has no credential, vendor HTTP, browser, or profile-create surface.
    """
    bound_doc, problems = sb.load_bindings()
    if problems or bound_doc is None:
        raise SetupRefusal(
            "enroll all three Chairman ChatGPT seats before bootstrapping "
            "the disposable peer lifecycle"
        )
    anchor_row = _matching_local_row(bound_doc)
    if anchor_row.get("running") is True:
        raise SetupRefusal(
            "the disposable anchor must be stopped before lifecycle bootstrap"
        )
    if input(
        f"Type {_CONFIRM_BOOTSTRAP_PEER!r} to bootstrap only the existing "
        "disposable peer lifecycle: "
    ).strip() != _CONFIRM_BOOTSTRAP_PEER:
        raise SetupRefusal(
            "peer-bootstrap confirmation did not match; no state was written"
        )
    # The operator may spend arbitrary time at the confirmation prompt. Mint
    # only from fresh canonical binding and anchor bytes parsed through the
    # no-follow descriptors retained by the one-use evidence capability. The
    # mint also repeats the exact stopped/non-seat census proof.
    authorization = vendors.mint_coordinator_peer_bootstrap_evidence()
    if authorization is None:
        raise SetupRefusal(
            "the exact post-confirmation bootstrap evidence could not be proven"
        )
    outcome = vendors.run_coordinator_peer_bootstrap(
        authorization=authorization,
    )
    if outcome not in (vendors.CREATED_THIS_CALL, vendors.EXISTING_EXACT):
        raise SetupRefusal(
            "the exact first-rollout bootstrap state could not be proven"
        )
    print(f"Peer lifecycle bootstrap: {outcome}. No profile or vendor effect occurred.")
    return 0


def rollback_peer_interactive() -> int:
    """Remove only the exact operation-created disposable peer profile.

    This coordinator never reads the credential, never constructs vendor
    HTTP, and never sees a raw vendor response — it only forwards the exit
    code and lets ``vendors.main`` print its own receipt.
    """
    if not vendors.coordinator_peer_paths_safe("rollback-peer-profile"):
        raise SetupRefusal("peer lifecycle paths are unsafe or inconsistent")
    if not vendors.coordinator_peer_rollback_receipt_ready():
        raise SetupRefusal("trusted fresh downstream ownership release receipt is required")
    bound_doc, problems = sb.load_bindings()
    if problems or bound_doc is None:
        raise SetupRefusal("enroll all three Chairman ChatGPT seats before rolling back a disposable peer profile")
    _matching_local_row(bound_doc)
    if input(f"Type {_CONFIRM_ROLLBACK_PEER!r} to remove the operation-created peer profile: ").strip() != _CONFIRM_ROLLBACK_PEER:
        raise SetupRefusal("peer-rollback confirmation did not match; nothing was dispatched")
    return vendors.run_coordinator_peer_rollback([
        "--vendor", "multilogin",
        "--provision-path", str(Path(canary.DEFAULT_PROVISION_PATH).expanduser()),
    ])


def status() -> int:
    census = _candidate_rows(chatgpt.list_local_environments())
    bindings, problems = sb.load_bindings()
    seats = set()
    if bindings is not None and not problems:
        seats = {
            row.get("seat_ref") for row in bindings.get("bindings", [])
            if isinstance(row, dict) and row.get("provider") == "chatgpt"
        } & set(SEAT_REFS)
    provision, code = _load_current_provision()
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
    configure_parser = sub.add_parser(
        "configure-canary-port", help="apply the one exact disposable Multilogin port policy",
    )
    configure_parser.add_argument(
        "--vendor", default="multilogin", choices=("multilogin", "gologin"),
    )
    run_parser = sub.add_parser("run-canary", help="run the accepted disposable canary")
    run_parser.add_argument("--vendor", default="multilogin", choices=("multilogin", "gologin"))
    create_peer_parser = sub.add_parser(
        "create-peer-profile", help="create the one missing stopped disposable peer profile",
    )
    create_peer_parser.add_argument("--vendor", default="multilogin", choices=("multilogin", "gologin"))
    sub.add_parser(
        "bootstrap-peer-lifecycle",
        help="bootstrap local lifecycle state for the exact existing stopped anchor",
    )
    rollback_peer_parser = sub.add_parser(
        "rollback-peer-profile", help="remove only the exact operation-created peer profile",
    )
    rollback_peer_parser.add_argument("--vendor", default="multilogin", choices=("multilogin", "gologin"))
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
        if args.command == "configure-canary-port":
            if args.vendor != "multilogin":
                raise SetupRefusal("fixed-port configuration is supported only for Multilogin")
            current_environment_snapshot = _acquire_current_environment_snapshot()
            provision, code = _load_current_provision(
                current_environment_snapshot=current_environment_snapshot,
            )
            if provision is None:
                provision, code = _migrate_legacy_provision(
                    canary.DEFAULT_PROVISION_PATH,
                    now=datetime.now(timezone.utc),
                    current_environment_snapshot=current_environment_snapshot,
                )
            if provision is None or provision.get("vendor") != "multilogin":
                raise SetupRefusal(
                    f"the exact disposable Multilogin provision is unavailable ({code})"
                )
            return vendors.main([
                "configure-canary-port",
                "--vendor", args.vendor,
                "--provision-path", str(Path(canary.DEFAULT_PROVISION_PATH).expanduser()),
            ])
        if args.command == "run-canary":
            return vendors.main([
                "run",
                "--vendor", args.vendor,
                "--provision-path", str(Path(canary.DEFAULT_PROVISION_PATH).expanduser()),
            ])
        if args.command == "create-peer-profile":
            if args.vendor != "multilogin":
                raise SetupRefusal("GoLogin peer profiles remain unsupported; no disposable peer profile will be created")
            return create_peer_interactive()
        if args.command == "bootstrap-peer-lifecycle":
            return bootstrap_peer_interactive()
        if args.command == "rollback-peer-profile":
            if args.vendor != "multilogin":
                raise SetupRefusal("GoLogin peer profiles remain unsupported; no disposable peer profile will be removed")
            return rollback_peer_interactive()
    except SetupRefusal as refusal:
        print(f"REFUSED: {refusal}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
