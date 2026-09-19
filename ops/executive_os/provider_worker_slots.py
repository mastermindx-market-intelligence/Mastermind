"""Reviewed, secret-free Executive Codex worker realm inventory.

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
from typing import Any, Sequence

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
_SUBSCRIPTION_SLOT_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*-[0-9]{2}$")
_WORKER_USER_RE = re.compile(r"^_mastermind_[a-z0-9_]+$")


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

    @property
    def auth_path(self) -> Path:
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
    """Held provider-plan seat; not part of the proven Codex slot inventory."""

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
    admission_state: str = "HELD_FOR_REAL_CANARY"

    def public_descriptor(self) -> dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "provider": self.provider,
            "profile_id": self.profile_id,
            "harness_binding_id": self.harness_binding_id,
            "worker_user": self.worker_user,
            "worker_uid": self.worker_uid,
            "worker_gid": self.worker_gid,
            "admission_state": self.admission_state,
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
        worker_uid=458,
        worker_gid=458,
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
        worker_uid=459,
        worker_gid=459,
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


def get_slot(slot_id: str) -> ProviderWorkerSlot:
    if not isinstance(slot_id, str) or _SLOT_ID_RE.fullmatch(slot_id) is None:
        raise SlotCatalogError("unknown_slot")
    for row in all_slots():
        if row.slot_id == slot_id:
            return row
    raise SlotCatalogError("unknown_slot")


def validate_subscription_slots(
    rows: Sequence[SubscriptionWorkerSlot],
) -> tuple[SubscriptionWorkerSlot, ...]:
    catalog = tuple(rows)
    expected = {
        "alibaba-token-01": {
            "provider": "alibaba",
            "profile_id": "alibaba-token-plan-personal",
            "harness_binding_id": "alibaba-token-plan-personal.codex-responses",
            "worker_user": "_mastermind_alibaba_01",
            "worker_uid": 458,
        },
        "minimax-token-01": {
            "provider": "minimax",
            "profile_id": "minimax-token-plan",
            "harness_binding_id": "minimax-token-plan.codex-responses",
            "worker_user": "_mastermind_minimax_01",
            "worker_uid": 459,
        },
    }
    if tuple(row.slot_id for row in catalog) != tuple(expected):
        raise SlotCatalogError("subscription_slot_inventory_invalid")
    for field in (
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
    ):
        _unique(catalog, field)

    legacy = all_slots()
    reserved_uids = {450, 452, 457} | {slot.worker_uid for slot in legacy}
    reserved_gids = {450, 452, 457} | {slot.worker_gid for slot in legacy}
    legacy_homes = {slot.provider_home for slot in legacy}
    for row in catalog:
        wanted = expected[row.slot_id]
        if (
            _SUBSCRIPTION_SLOT_ID_RE.fullmatch(row.slot_id) is None
            or row.provider != wanted["provider"]
            or row.profile_id != wanted["profile_id"]
            or row.harness_binding_id != wanted["harness_binding_id"]
            or row.worker_user != wanted["worker_user"]
            or _WORKER_USER_RE.fullmatch(row.worker_user) is None
            or row.worker_group != row.worker_user
            or row.worker_uid != wanted["worker_uid"]
            or row.worker_gid != wanted["worker_uid"]
            or row.provider_home != RUNTIME_WORKER_ROOT / row.slot_id / "provider-home"
            or row.worker_config != SYSTEM_CONFIG_ROOT / f"worker-{row.slot_id}.json"
            or row.admission_state != "HELD_FOR_REAL_CANARY"
        ):
            raise SlotCatalogError("subscription_slot_invalid")
        if row.worker_uid in reserved_uids:
            raise SlotCatalogError("subscription_worker_uid_collision")
        if row.worker_gid in reserved_gids:
            raise SlotCatalogError("subscription_worker_gid_collision")
        if row.provider_home in legacy_homes:
            raise SlotCatalogError("subscription_provider_home_collision")
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
    parser.add_argument("slot_id", choices=[row.slot_id for row in all_slots()])
    parser.add_argument("field", choices=sorted(_RESOLVABLE_FIELDS))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        value = resolve_field(args.slot_id, args.field)
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
    "resolve_field",
    "subscription_slots",
    "validate_slots",
    "validate_subscription_slots",
]


if __name__ == "__main__":
    raise SystemExit(main())
