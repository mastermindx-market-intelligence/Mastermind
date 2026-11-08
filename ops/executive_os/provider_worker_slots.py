"""Reviewed, secret-free Executive provider worker realm inventory.

Provider account identifiers and Multilogin profile identifiers are private
host state and are deliberately absent.  ``oauth_seat_ref`` is only the
existing logical Chairman-seat label used to tell the operator which isolated
browser session should complete an initial device authorization.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

_SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if __package__ in {None, ""} and str(_SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIRECTORY))

try:
    from ops.executive_os.provider_identity_policy import (
        COMPANY_WORKSPACE_BINDING_CLASS,
        PERSONAL_PRO_WORKER_BINDING_CLASS,
    )
except ModuleNotFoundError:  # pragma: no cover - installed direct-script mode
    from provider_identity_policy import (  # type: ignore[no-redef]
        COMPANY_WORKSPACE_BINDING_CLASS,
        PERSONAL_PRO_WORKER_BINDING_CLASS,
    )


SYSTEM_CONFIG_ROOT = Path("/Library/Application Support/MastermindExecutive/config")
RUNTIME_WORKER_ROOT = Path("/var/db/mastermind-executive/workers")
WORKER_GROUP = "_mastermind_worker"
WORKER_GID = 451
_SLOT_ID_RE = re.compile(r"^codex(?:-pro)?-[0-9]{2}$")
_SUBSCRIPTION_SLOT_ID_RE = re.compile(r"^(?:alibaba|minimax)-token-[0-9]{2}$")
_WORKER_USER_RE = re.compile(r"^_mastermind_[a-z0-9_]+$")
# Accepted local labels, not enrolled Workers or provider-capacity identities.
# The legacy label remains compatible; new labels never select a numbered login.
_NATIVE_CLAUDE_SLOT_IDS = frozenset({
    "claude8-native-01", "claude-native-01", "claude-native-02",
    "claude-native-03", "claude-native-04",
})


class SlotCatalogError(ValueError):
    """Bounded catalog/configuration refusal."""


@dataclass(frozen=True)
class ProviderWorkerSlot:
    slot_id: str
    worker_user: str
    worker_group: str
    worker_uid: int
    worker_gid: int
    provider_home: Path
    readiness_receipt: Path
    workspace_binding_class: str
    allowed_credential_kinds: tuple[str, ...]
    oauth_seat_ref: str | None
    provider_family: str = "openai"

    @property
    def auth_path(self) -> Path:
        if self.provider_family == "anthropic":
            return self.provider_home / ".claude" / ".credentials.json"
        if self.provider_family == "deepseek":
            raise SlotCatalogError("native_provider_owns_credential_storage")
        return self.provider_home / "auth.json"

    @property
    def default_credential_kind(self) -> str:
        return self.allowed_credential_kinds[0]

    def public_descriptor(self) -> dict[str, Any]:
        """Return reviewed non-provider identity for sanitized status output."""

        return {
            "slot_id": self.slot_id,
            "worker_user": self.worker_user,
            "worker_uid": self.worker_uid,
            "worker_gid": self.worker_gid,
            "workspace_binding_class": self.workspace_binding_class,
            "allowed_credential_kinds": list(self.allowed_credential_kinds),
            "oauth_seat_ref": self.oauth_seat_ref,
        }


@dataclass(frozen=True)
class SubscriptionWorkerSlot:
    """Reviewed local principal for a held Codex-backed subscription realm.

    This catalog owns only host identity/config coordinates. Provider account,
    Capacity capability/generation, readiness, routing and autonomous admission
    remain with their existing owners.
    """

    slot_id: str
    provider: str
    profile_id: str
    harness_binding_id: str
    worker_user: str
    worker_group: str
    worker_uid: int
    worker_gid: int
    provider_home: Path
    worker_config: Path

    def public_descriptor(self) -> dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "provider": self.provider,
            "profile_id": self.profile_id,
            "harness_binding_id": self.harness_binding_id,
            "worker_user": self.worker_user,
            "worker_uid": self.worker_uid,
            "worker_gid": self.worker_gid,
            "admission_state": "HELD_FOR_REAL_CANARY",
        }


_SLOTS = (
    ProviderWorkerSlot(
        slot_id="codex-01",
        worker_user="_mastermind_worker",
        worker_group=WORKER_GROUP,
        worker_uid=451,
        worker_gid=WORKER_GID,
        provider_home=RUNTIME_WORKER_ROOT / "codex-01" / "provider-home",
        readiness_receipt=SYSTEM_CONFIG_ROOT / "provider-readiness-v2.json",
        workspace_binding_class=COMPANY_WORKSPACE_BINDING_CLASS,
        allowed_credential_kinds=(
            "service-account",
            "personal-access-token",
            "device-auth",
        ),
        oauth_seat_ref=None,
    ),
    *(
        ProviderWorkerSlot(
            slot_id=f"codex-pro-{index:02d}",
            worker_user=f"_mastermind_codex_{index:02d}",
            worker_group=f"_mastermind_codex_{index:02d}",
            worker_uid=453 + index,
            worker_gid=453 + index,
            provider_home=RUNTIME_WORKER_ROOT
            / f"codex-pro-{index:02d}"
            / "provider-home",
            readiness_receipt=SYSTEM_CONFIG_ROOT
            / f"provider-readiness-codex-pro-{index:02d}-v2.json",
            workspace_binding_class=PERSONAL_PRO_WORKER_BINDING_CLASS,
            allowed_credential_kinds=("device-auth",),
            oauth_seat_ref=f"chatgpt{index}",
        )
        for index in range(1, 4)
    ),

)


_SUBSCRIPTION_SLOTS = (
    SubscriptionWorkerSlot(
        slot_id="alibaba-token-01",
        provider="alibaba",
        profile_id="alibaba-token-plan-personal",
        harness_binding_id="alibaba-token-plan-personal.codex-responses",
        worker_user="_mastermind_alibaba_01",
        worker_group="_mastermind_alibaba_01",
        worker_uid=459,
        worker_gid=459,
        provider_home=RUNTIME_WORKER_ROOT / "alibaba-token-01" / "provider-home",
        worker_config=SYSTEM_CONFIG_ROOT / "worker-alibaba-token-01.json",
    ),
    SubscriptionWorkerSlot(
        slot_id="minimax-token-01",
        provider="minimax",
        profile_id="minimax-token-plan",
        harness_binding_id="minimax-token-plan.codex-responses",
        worker_user="_mastermind_minimax_01",
        worker_group="_mastermind_minimax_01",
        worker_uid=460,
        worker_gid=460,
        provider_home=RUNTIME_WORKER_ROOT / "minimax-token-01" / "provider-home",
        worker_config=SYSTEM_CONFIG_ROOT / "worker-minimax-token-01.json",
    ),
)


def _unique(rows: Sequence[Any], field: str) -> None:
    values = [getattr(row, field) for row in rows]
    if len(values) != len(set(values)):
        raise SlotCatalogError(f"duplicate_{field}")


def validate_slots(rows: Sequence[ProviderWorkerSlot]) -> tuple[ProviderWorkerSlot, ...]:
    catalog = tuple(rows)
    expected_ids = ("codex-01", "codex-pro-01", "codex-pro-02", "codex-pro-03")
    if tuple(row.slot_id for row in catalog) != expected_ids:
        raise SlotCatalogError("slot_inventory_invalid")
    for field in (
        "slot_id",
        "worker_user",
        "worker_group",
        "worker_uid",
        "worker_gid",
        "provider_home",
        "readiness_receipt",
    ):
        _unique(catalog, field)
    if len({row.auth_path for row in catalog}) != len(catalog):
        raise SlotCatalogError("duplicate_auth_path")

    expected_seats = (None, "chatgpt1", "chatgpt2", "chatgpt3")
    if tuple(row.oauth_seat_ref for row in catalog) != expected_seats:
        raise SlotCatalogError("oauth_seat_inventory_invalid")

    for index, row in enumerate(catalog):
        if _SLOT_ID_RE.fullmatch(row.slot_id) is None:
            raise SlotCatalogError("slot_id_invalid")
        if _WORKER_USER_RE.fullmatch(row.worker_user) is None:
            raise SlotCatalogError("worker_user_invalid")
        if _WORKER_USER_RE.fullmatch(row.worker_group) is None:
            raise SlotCatalogError("worker_group_invalid")
        if isinstance(row.worker_uid, bool) or not 400 <= row.worker_uid < 500:
            raise SlotCatalogError("worker_uid_invalid")
        if isinstance(row.worker_gid, bool) or not 400 <= row.worker_gid < 500:
            raise SlotCatalogError("worker_gid_invalid")
        if row.provider_home != RUNTIME_WORKER_ROOT / row.slot_id / "provider-home":
            raise SlotCatalogError("provider_home_invalid")
        if not row.readiness_receipt.is_absolute():
            raise SlotCatalogError("readiness_receipt_invalid")
        if index == 0:
            if (
                row.worker_uid != 451
                or row.worker_group != WORKER_GROUP
                or row.worker_gid != WORKER_GID
                or row.workspace_binding_class != COMPANY_WORKSPACE_BINDING_CLASS
                or row.oauth_seat_ref is not None
                or row.allowed_credential_kinds
                != ("service-account", "personal-access-token", "device-auth")
            ):
                raise SlotCatalogError("company_slot_invalid")
        elif (
            row.worker_uid != 453 + index
            or row.worker_group != row.worker_user
            or row.worker_gid != 453 + index
            or row.workspace_binding_class != PERSONAL_PRO_WORKER_BINDING_CLASS
            or row.allowed_credential_kinds != ("device-auth",)
            or row.oauth_seat_ref != f"chatgpt{index}"
        ):
            raise SlotCatalogError("personal_pro_slot_invalid")
    return catalog


def all_slots() -> tuple[ProviderWorkerSlot, ...]:
    return validate_slots(_SLOTS)


def validate_subscription_slots(
    rows: Sequence[SubscriptionWorkerSlot],
) -> tuple[SubscriptionWorkerSlot, ...]:
    catalog = tuple(rows)
    if tuple(row.slot_id for row in catalog) != (
        "alibaba-token-01",
        "minimax-token-01",
    ):
        raise SlotCatalogError("subscription_slot_inventory_invalid")
    for row in catalog:
        if type(row.worker_uid) is not int or type(row.worker_gid) is not int:
            raise SlotCatalogError("subscription_numeric_identity_invalid")
    for field in (
        "slot_id",
        "worker_user",
        "worker_group",
        "worker_uid",
        "worker_gid",
        "provider_home",
        "worker_config",
    ):
        _unique(catalog, field)
    expected = (
        (
            "alibaba-token-01",
            "alibaba",
            "alibaba-token-plan-personal",
            "alibaba-token-plan-personal.codex-responses",
            "_mastermind_alibaba_01",
            459,
        ),
        (
            "minimax-token-01",
            "minimax",
            "minimax-token-plan",
            "minimax-token-plan.codex-responses",
            "_mastermind_minimax_01",
            460,
        ),
    )
    legacy = all_slots()
    legacy_uids = {row.worker_uid for row in legacy}
    legacy_gids = {row.worker_gid for row in legacy}
    legacy_homes = {row.provider_home for row in legacy}
    for row, identity in zip(catalog, expected):
        slot_id, provider, profile_id, binding_id, worker_user, numeric_id = identity
        if (
            _SUBSCRIPTION_SLOT_ID_RE.fullmatch(row.slot_id) is None
            or row.slot_id != slot_id
            or row.provider != provider
            or row.profile_id != profile_id
            or row.harness_binding_id != binding_id
            or row.worker_user != worker_user
            or row.worker_group != worker_user
            or row.worker_uid != numeric_id
            or row.worker_gid != numeric_id
            or row.provider_home
            != RUNTIME_WORKER_ROOT / row.slot_id / "provider-home"
            or row.worker_config
            != SYSTEM_CONFIG_ROOT / f"worker-{row.slot_id}.json"
        ):
            raise SlotCatalogError("subscription_slot_invalid")
        if (
            row.worker_uid in legacy_uids
            or row.worker_gid in legacy_gids
            or row.provider_home in legacy_homes
        ):
            raise SlotCatalogError("subscription_slot_collision")
    return catalog


def subscription_slots() -> tuple[SubscriptionWorkerSlot, ...]:
    return validate_subscription_slots(_SUBSCRIPTION_SLOTS)


def get_subscription_slot(slot_id: str) -> SubscriptionWorkerSlot:
    if not isinstance(slot_id, str) or _SUBSCRIPTION_SLOT_ID_RE.fullmatch(slot_id) is None:
        raise SlotCatalogError("unknown_subscription_slot")
    for row in subscription_slots():
        if row.slot_id == slot_id:
            return row
    raise SlotCatalogError("unknown_subscription_slot")


def native_slot_from_config(config: Mapping[str, Any]) -> ProviderWorkerSlot:
    """Project one native slot from the existing root-owned broker config.

    This is structural validation, not authority. The realm owner must read
    and pin the actual root-owned config before calling it. OS identities are
    provisioned host state; they are never new source-code defaults.
    """
    enrollment = config.get("native_realm_enrollment")
    slot_id = enrollment.get("slot_id") if isinstance(enrollment, Mapping) else None
    if config.get("native_provider") == "codex" and slot_id == "codex-pro-04":
        # An inert fourth Personal Pro definition: all OS principal values
        # come from the already root-pinned worker config and are verified by
        # NativeRealmIdentityOwner under its existing UID/GID/HOME/binary gates.
        # This projection cannot provision a user or make a worker READY.
        uid, gid = config.get("worker_uid"), config.get("worker_gid")
        name, control = config.get("worker_user"), config.get("control_uid")
        existing = all_slots()
        home = RUNTIME_WORKER_ROOT / slot_id / "provider-home"
        if (type(uid) is not int or uid <= 0
                or type(gid) is not int or gid != uid
                or type(control) is not int or control <= 0 or control == uid
                or type(name) is not str or _WORKER_USER_RE.fullmatch(name) is None
                or type(config.get("provider_home")) is not str
                or config["provider_home"] != str(home)
                or uid in {s.worker_uid for s in existing}
                or gid in {s.worker_gid for s in existing}
                or control in {s.worker_uid for s in existing}
                or name in {s.worker_user for s in existing}):
            raise SlotCatalogError("native_codex_additional_principal_invalid")
        row = ProviderWorkerSlot(
            slot_id=slot_id, worker_user=name, worker_group=name,
            worker_uid=uid, worker_gid=gid, provider_home=home,
            readiness_receipt=SYSTEM_CONFIG_ROOT / (
                f"provider-readiness-{slot_id}-v2.json"),
            workspace_binding_class=PERSONAL_PRO_WORKER_BINDING_CLASS,
            allowed_credential_kinds=("device-auth",),
            oauth_seat_ref="chatgpt4",
            provider_family="openai",
        )
        for field in ("slot_id", "worker_user", "worker_group", "worker_uid",
                      "worker_gid", "provider_home", "readiness_receipt"):
            _unique(existing + (row,), field)
        return row
    if config.get("native_provider") == "deepseek":
        # A projection of the original root-enrolled principal, never a new
        # numbered account/seat, credential path, enrollment or READY assertion.
        uid, gid, name = (config.get(k) for k in ("worker_uid", "worker_gid", "worker_user"))
        control, home_value = config.get("control_uid"), config.get("provider_home")
        if (type(slot_id) is not str
                or re.fullmatch(r"deepseek-native-[a-z0-9][a-z0-9-]{0,47}", slot_id) is None
                or type(uid) is not int or uid <= 0
                or type(gid) is not int or gid <= 0
                or type(control) is not int or control <= 0 or control == uid
                or type(name) is not str or _WORKER_USER_RE.fullmatch(name) is None
                or type(home_value) is not str or not Path(home_value).is_absolute()
                or str(Path(home_value)) != home_value or ".." in Path(home_value).parts):
            raise SlotCatalogError("native_deepseek_principal_invalid")
        row = ProviderWorkerSlot(
            slot_id=slot_id, worker_user=name, worker_group=name,
            worker_uid=uid, worker_gid=gid, provider_home=Path(home_value),
            readiness_receipt=SYSTEM_CONFIG_ROOT / f"provider-readiness-{slot_id}.json",
            workspace_binding_class="native_deepseek_account",
            allowed_credential_kinds=("provider-owned-account",),
            oauth_seat_ref=None, provider_family="deepseek",
        )
        existing = all_slots()
        if control in {s.worker_uid for s in existing}:
            raise SlotCatalogError("native_deepseek_control_collision")
        for field in ("slot_id", "worker_user", "worker_group", "worker_uid", "worker_gid",
                      "provider_home", "readiness_receipt"):
            _unique(existing + (row,), field)
        return row
    if (config.get("native_provider") != "claude"
            or type(slot_id) is not str or slot_id not in _NATIVE_CLAUDE_SLOT_IDS):
        raise SlotCatalogError("native_slot_inventory_invalid")
    worker_user = config.get("worker_user")
    worker_uid, worker_gid = config.get("worker_uid"), config.get("worker_gid")
    if (not isinstance(worker_user, str) or not _WORKER_USER_RE.fullmatch(worker_user)
            or type(worker_uid) is not int or worker_uid <= 0
            or type(worker_gid) is not int or worker_gid <= 0
            or type(config.get("control_uid")) is not int
            or worker_uid == config["control_uid"]):
        raise SlotCatalogError("native_slot_identity_invalid")
    row = ProviderWorkerSlot(
        slot_id=enrollment["slot_id"], worker_user=worker_user,
        worker_group=worker_user, worker_uid=worker_uid, worker_gid=worker_gid,
        provider_home=RUNTIME_WORKER_ROOT / enrollment["slot_id"] / "provider-home",
        readiness_receipt=SYSTEM_CONFIG_ROOT / f"provider-readiness-{enrollment['slot_id']}.json",
        workspace_binding_class="native_claude_subscription",
        allowed_credential_kinds=("claudeai-subscription",),
        oauth_seat_ref="claude8" if slot_id == "claude8-native-01" else None,
        provider_family="anthropic",
    )
    for field in ("slot_id", "worker_user", "worker_group", "worker_uid", "worker_gid",
                  "provider_home", "readiness_receipt"):
        _unique(all_slots() + (row,), field)
    return row


def get_slot(slot_id: str) -> ProviderWorkerSlot:
    if not isinstance(slot_id, str) or _SLOT_ID_RE.fullmatch(slot_id) is None:
        raise SlotCatalogError("unknown_slot")
    for row in all_slots():
        if row.slot_id == slot_id:
            return row
    raise SlotCatalogError("unknown_slot")


_SUBSCRIPTION_RESOLVABLE_FIELDS = frozenset(
    {
        "slot_id",
        "provider",
        "profile_id",
        "harness_binding_id",
        "worker_user",
        "worker_group",
        "worker_uid",
        "worker_gid",
        "provider_home",
        "worker_config",
    }
)


def resolve_subscription_field(slot_id: str, field: str) -> str:
    if field not in _SUBSCRIPTION_RESOLVABLE_FIELDS:
        raise SlotCatalogError("unknown_subscription_field")
    return str(getattr(get_subscription_slot(slot_id), field))


_RESOLVABLE_FIELDS = frozenset(
    {
        "slot_id",
        "worker_user",
        "worker_group",
        "worker_uid",
        "worker_gid",
        "provider_home",
        "readiness_receipt",
        "workspace_binding_class",
        "default_credential_kind",
        "oauth_seat_ref",
    }
)


def resolve_field(slot_id: str, field: str) -> str:
    if field not in _RESOLVABLE_FIELDS:
        raise SlotCatalogError("unknown_field")
    value = getattr(get_slot(slot_id), field)
    if value is None:
        return ""
    return str(value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve one reviewed provider worker slot field")
    parser.add_argument("--subscription", action="store_true")
    # Select and validate only the explicit catalog inside main's refusal boundary.
    parser.add_argument("slot_id")
    parser.add_argument("field")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        value = (
            resolve_subscription_field(args.slot_id, args.field)
            if args.subscription
            else resolve_field(args.slot_id, args.field)
        )
    except SlotCatalogError:
        return 2
    sys.stdout.write(value + "\n")
    return 0


__all__ = [
    "ProviderWorkerSlot",
    "SubscriptionWorkerSlot",
    "RUNTIME_WORKER_ROOT",
    "SYSTEM_CONFIG_ROOT",
    "SlotCatalogError",
    "WORKER_GID",
    "WORKER_GROUP",
    "all_slots",
    "get_slot",
    "get_subscription_slot",
    "main",
    "native_slot_from_config",
    "resolve_field",
    "resolve_subscription_field",
    "subscription_slots",
    "validate_slots",
    "validate_subscription_slots",
]


if __name__ == "__main__":
    raise SystemExit(main())
