"""Create and verify the Chairman-physical CEO submit-arm receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "mastermind.executive_submit_arm_receipt/v1"
MANIFEST_NAME = ".executive-release-manifest.json"
RECEIPT_MAX_AGE_SECONDS = 300


class SubmitArmReceiptError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SubmitArmReceiptError("receipt_invalid") from exc
    if not isinstance(value, dict):
        raise SubmitArmReceiptError("receipt_invalid")
    return value


def _manifest(release_root: Path) -> tuple[Path, dict[str, Any]]:
    path = release_root / MANIFEST_NAME
    try:
        value = _json(path)
    except SubmitArmReceiptError as exc:
        raise SubmitArmReceiptError("release_manifest_invalid") from exc
    commit = value.get("commit_sha")
    if not isinstance(commit, str) or len(commit) != 40:
        raise SubmitArmReceiptError("release_manifest_invalid")
    return path, value


def _config_uid(config_path: Path) -> int:
    config = _json(config_path)
    uid = config.get("control_uid")
    if type(uid) is not int or uid < 0:
        raise SubmitArmReceiptError("config_invalid")
    return uid


def make_receipt(config_path: Path, release_root: Path, *, principal_uid: int, now: datetime) -> dict[str, Any]:
    manifest, value = _manifest(release_root)
    return {
        "schema_version": SCHEMA_VERSION,
        "observed_at": now.astimezone(UTC).isoformat(timespec="seconds"),
        "release_commit_sha": value["commit_sha"],
        "release_manifest_sha256": _sha256_file(manifest),
        "config_sha256": _sha256_file(config_path),
        "principal": {"effective_uid": principal_uid, "effective_gid": os.getegid()},
        "armed_scope": "ceo_submit",
    }


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise SubmitArmReceiptError("receipt_invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SubmitArmReceiptError("receipt_invalid") from exc
    if parsed.tzinfo is None:
        raise SubmitArmReceiptError("receipt_invalid")
    return parsed.astimezone(UTC)


def verify(receipt_path: Path, config_path: Path, release_root: Path, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    try:
        receipt_info = receipt_path.lstat()
    except OSError:
        raise SubmitArmReceiptError("receipt_absent")
    expected_uid = _config_uid(config_path)
    if (
        stat.S_ISLNK(receipt_info.st_mode)
        or not stat.S_ISREG(receipt_info.st_mode)
        or stat.S_IMODE(receipt_info.st_mode) & 0o022
        or receipt_info.st_uid not in {expected_uid, 0}
    ):
        raise SubmitArmReceiptError("receipt_not_private")
    value = _json(receipt_path)
    observed = _parse_time(value.get("observed_at"))
    age = (now.astimezone(UTC) - observed).total_seconds()
    if age < 0 or age > RECEIPT_MAX_AGE_SECONDS:
        raise SubmitArmReceiptError("receipt_stale")
    manifest, manifest_value = _manifest(release_root)
    principal = value.get("principal")
    if not isinstance(principal, dict) or principal.get("effective_uid") != expected_uid:
        raise SubmitArmReceiptError("receipt_wrong_principal")
    if value.get("release_commit_sha") != manifest_value["commit_sha"] or value.get("release_manifest_sha256") != _sha256_file(manifest):
        raise SubmitArmReceiptError("receipt_wrong_release")
    if value.get("config_sha256") != _sha256_file(config_path) or value.get("schema_version") != SCHEMA_VERSION or value.get("armed_scope") != "ceo_submit":
        raise SubmitArmReceiptError("receipt_invalid")
    return value


def _atomic_write(path: Path, value: dict[str, Any], owner_uid: int) -> None:
    parent = path.parent
    if not parent.is_dir() or stat.S_ISLNK(parent.lstat().st_mode):
        raise SubmitArmReceiptError("receipt_parent_invalid")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o400)
        os.chown(temporary, owner_uid, os.getegid())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def emit(receipt_path: Path, config_path: Path, release_root: Path, *, now: datetime | None = None) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise SubmitArmReceiptError("emit_requires_root")
    manifest, manifest_value = _manifest(release_root)
    if not re.fullmatch(r"[0-9a-fA-F]{40}", release_root.name) or release_root.name != manifest_value["commit_sha"]:
        raise SubmitArmReceiptError("release_mismatch")
    config_uid = _config_uid(config_path)
    configured_release = _json(config_path).get("release_commit_sha")
    if isinstance(configured_release, str) and configured_release != manifest_value["commit_sha"]:
        raise SubmitArmReceiptError("release_mismatch")
    value = make_receipt(config_path, release_root, principal_uid=config_uid, now=now or datetime.now(UTC))
    _atomic_write(receipt_path, value, config_uid)
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("verify", "emit"))
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        value = verify(args.receipt, args.config, args.release_root) if args.command == "verify" else emit(args.receipt, args.config, args.release_root)
    except SubmitArmReceiptError as exc:
        print(str(exc))
        return 2
    print(json.dumps({"ok": True, "schema_version": value["schema_version"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
