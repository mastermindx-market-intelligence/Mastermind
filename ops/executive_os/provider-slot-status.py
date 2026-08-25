#!/usr/bin/env python3
"""Sanitized status for reviewed Executive Codex worker realms.

Credential bytes are never opened.  The only credential observation is the
same exact ``lstat`` metadata boundary used by provider readiness.  Output is
closed to reviewed booleans, bounded state/refusal codes, the logical slot,
and the non-secret Chairman-seat reference used for initial device OAuth.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Sequence


_SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if __package__ in {None, ""} and str(_SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIRECTORY))

try:
    from ops.executive_os import provider_readiness as readiness
    from ops.executive_os import provider_worker_slots as worker_slots
except ModuleNotFoundError:  # pragma: no cover - installed direct-script mode
    import provider_readiness as readiness  # type: ignore[no-redef]
    import provider_worker_slots as worker_slots  # type: ignore[no-redef]


STATUS_FIELDS = frozenset(
    {
        "slot_id",
        "oauth_seat_ref",
        "provider_home_present",
        "provider_home_metadata_valid",
        "credential_present",
        "credential_metadata_valid",
        "readiness_receipt_present",
        "readiness_receipt_metadata_valid",
        "readiness_state",
        "readiness_refusal",
        "worker_process_present",
    }
)
_SAFE_REFUSAL = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _lstat_present(path: Path) -> bool:
    try:
        path.lstat()
    except OSError:
        return False
    return True


def _directory_metadata_valid(path: Path, *, uid: int, gid: int) -> bool:
    try:
        info = path.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != uid
            or info.st_gid != gid
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            return False
        readiness._assert_no_macos_acl(path)
    except (OSError, readiness.ReadinessError):
        return False
    return True


def _credential_metadata_valid(
    path: Path, *, worker_uid: int, worker_gid: int
) -> bool:
    try:
        readiness.current_auth_identity(
            path, worker_uid=worker_uid, worker_gid=worker_gid
        )
    except (OSError, readiness.ReadinessError):
        return False
    return True


def _receipt_metadata_valid(path: Path) -> bool:
    try:
        readiness.lstat_identity(
            path,
            expected_uid=0,
            expected_gid=0,
            expected_mode=0o400,
            require_nonempty=True,
        )
    except (OSError, readiness.ReadinessError):
        return False
    return True


def _bounded_refusal(exc: BaseException) -> str:
    candidate = str(exc)
    if _SAFE_REFUSAL.fullmatch(candidate) is not None:
        return candidate
    return "readiness_invalid"


def worker_process_present(worker_uid: int) -> bool:
    try:
        completed = subprocess.run(
            ["/usr/bin/pgrep", "-U", str(worker_uid)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def inspect_slot(
    slot: worker_slots.ProviderWorkerSlot,
    *,
    process_probe: Callable[[int], bool] = worker_process_present,
) -> dict[str, Any]:
    home_present = _lstat_present(slot.provider_home)
    credential_present = _lstat_present(slot.auth_path)
    receipt_present = _lstat_present(slot.readiness_receipt)
    home_valid = home_present and _directory_metadata_valid(
        slot.provider_home, uid=slot.worker_uid, gid=slot.worker_gid
    )
    credential_valid = credential_present and _credential_metadata_valid(
        slot.auth_path, worker_uid=slot.worker_uid, worker_gid=slot.worker_gid
    )
    receipt_valid = receipt_present and _receipt_metadata_valid(
        slot.readiness_receipt
    )

    readiness_state = "not_ready"
    readiness_refusal: str | None
    if not receipt_present:
        readiness_state = "missing"
        readiness_refusal = "readiness_receipt_missing"
    elif not home_valid:
        readiness_refusal = "provider_home_metadata_invalid"
    elif not credential_valid:
        readiness_refusal = "credential_metadata_invalid"
    elif not receipt_valid:
        readiness_refusal = "readiness_receipt_metadata_invalid"
    else:
        try:
            readiness.validate_receipt_file(
                slot.readiness_receipt,
                auth_path=slot.auth_path,
                expected_kind=slot.default_credential_kind,
                workspace_binding_class=slot.workspace_binding_class,
                worker_uid=slot.worker_uid,
                worker_gid=slot.worker_gid,
            )
        except (OSError, readiness.ReadinessError) as exc:
            readiness_refusal = _bounded_refusal(exc)
        else:
            readiness_state = "ready"
            readiness_refusal = None

    try:
        process_present = bool(process_probe(slot.worker_uid))
    except Exception:  # pragma: no cover - custom probes must not widen output
        process_present = False

    result = {
        "slot_id": slot.slot_id,
        "oauth_seat_ref": slot.oauth_seat_ref,
        "provider_home_present": home_present,
        "provider_home_metadata_valid": home_valid,
        "credential_present": credential_present,
        "credential_metadata_valid": credential_valid,
        "readiness_receipt_present": receipt_present,
        "readiness_receipt_metadata_valid": receipt_valid,
        "readiness_state": readiness_state,
        "readiness_refusal": readiness_refusal,
        "worker_process_present": process_present,
    }
    if set(result) != STATUS_FIELDS:  # fail closed if output surface drifts
        raise RuntimeError("status_fields_invalid")
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show sanitized status for reviewed provider worker slots"
    )
    parser.add_argument(
        "--slot-id",
        choices=[slot.slot_id for slot in worker_slots.all_slots()],
        help="show one reviewed slot; default is every slot",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    slots = (
        (worker_slots.get_slot(args.slot_id),)
        if args.slot_id is not None
        else worker_slots.all_slots()
    )
    json.dump(
        [inspect_slot(slot) for slot in slots],
        sys.stdout,
        sort_keys=True,
        separators=(",", ":"),
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
