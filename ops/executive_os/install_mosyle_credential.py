"""Install the fixed Mosyle read-only credential from non-terminal stdin.

This is a local administrator ceremony only.  The secret is never accepted as
an argv flag and is never printed.  The target identity is consumed from the
existing sealed Executive MCP install configuration.
"""
from __future__ import annotations

import argparse
import json
import os
import pwd
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from integrations.mosyle_mdm import credential as credential_file  # noqa: E402

MCP_CONFIG = Path(
    "/Library/Application Support/MastermindExecutive/config/executive-mcp.json"
)
RECEIPT_SCHEMA = "mastermind.mosyle_credential_install.v1"


class InstallError(RuntimeError):
    pass


class InstallEffectUnknown(InstallError):
    pass


def _write_all(descriptor: int, value: bytes) -> None:
    offset = 0
    while offset < len(value):
        written = os.write(descriptor, value[offset:])
        if written <= 0:
            raise InstallError("Mosyle credential write failed")
        offset += written


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _canonical_payload(raw: bytes) -> bytes:
    parsed = credential_file._parse_credential(raw)
    value: dict[str, Any] = {
        "auth_mode": parsed.auth_mode,
        "access_token": parsed.access_token,
    }
    if parsed.email is not None:
        value["email"] = parsed.email
    if parsed.password is not None:
        value["password"] = parsed.password
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def install_credential(
    payload: bytes,
    *,
    target: Path,
    service_uid: int,
    service_gid: int,
    replace_existing: bool,
) -> str:
    canonical = _canonical_payload(payload)
    credential_file._validate_parent(target)
    exists = target.exists() or target.is_symlink()
    if exists:
        try:
            current = credential_file._read_credential_file(
                target,
                expected_uid=service_uid,
                expected_gid=service_gid,
            )
        except Exception as exc:
            raise InstallError(
                "existing Mosyle credential metadata is unsafe"
            ) from exc
        if current == canonical:
            return "ALREADY_INSTALLED"
        if not replace_existing:
            raise InstallError(
                "Mosyle credential exists; explicit replacement is required"
            )
    elif replace_existing:
        raise InstallError("Mosyle credential replacement target is absent")

    temporary = target.with_name(f".{target.name}.new.{os.getpid()}")
    if temporary.exists() or temporary.is_symlink():
        raise InstallError("Mosyle credential staging path is occupied")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor = -1
    replaced = False
    try:
        descriptor = os.open(temporary, flags, 0o600)
        os.fchown(descriptor, service_uid, service_gid)
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, canonical)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        staged = credential_file._read_credential_file(
            temporary,
            expected_uid=service_uid,
            expected_gid=service_gid,
        )
        if staged != canonical:
            raise InstallError("Mosyle credential staging verification failed")
        os.replace(temporary, target)
        replaced = True
        _fsync_directory(target.parent)
        installed = credential_file._read_credential_file(
            target,
            expected_uid=service_uid,
            expected_gid=service_gid,
        )
        if installed != canonical:
            raise InstallEffectUnknown(
                "Mosyle credential replacement could not be reconciled"
            )
        return "INSTALLED"
    except BaseException as exc:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if not replaced:
            try:
                temporary.unlink()
            except OSError:
                pass
        if replaced:
            if isinstance(exc, InstallEffectUnknown):
                raise
            raise InstallEffectUnknown(
                "Mosyle credential replacement effect is unknown"
            ) from exc
        if isinstance(exc, InstallError):
            raise
        raise InstallError("Mosyle credential installation failed") from exc


def _installed_service_identity() -> tuple[int, int]:
    from ops.executive_os.executive_mcp_entry import (
        require_sealed_path,
        validate_document,
    )

    require_sealed_path(MCP_CONFIG)
    try:
        raw = validate_document(json.loads(MCP_CONFIG.read_text(encoding="utf-8")))
        uid = int(raw["service_uid"])
        account = pwd.getpwuid(uid)
    except Exception as exc:
        raise InstallError("installed MCP service identity is unavailable") from exc
    if account.pw_uid != uid or account.pw_gid < 0:
        raise InstallError("installed MCP service identity is unavailable")
    return uid, int(account.pw_gid)


def _read_stdin() -> bytes:
    stream = getattr(sys.stdin, "buffer", sys.stdin)
    if hasattr(stream, "isatty") and stream.isatty():
        raise InstallError("Mosyle credential requires non-terminal stdin")
    raw = stream.read(credential_file.MAX_CREDENTIAL_BYTES + 1)
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if not isinstance(raw, (bytes, bytearray)):
        raise InstallError("Mosyle credential input is invalid")
    value = bytes(raw)
    if not value or len(value) > credential_file.MAX_CREDENTIAL_BYTES:
        raise InstallError("Mosyle credential input is invalid")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="replace a different already-valid credential",
    )
    args = parser.parse_args(argv)
    if os.geteuid() != 0:
        print("mosyle-credential: administrator privileges required", file=sys.stderr)
        return 77
    try:
        uid, gid = _installed_service_identity()
        status = install_credential(
            _read_stdin(),
            target=credential_file.CREDENTIAL_PATH,
            service_uid=uid,
            service_gid=gid,
            replace_existing=args.replace_existing,
        )
    except InstallEffectUnknown:
        print(
            json.dumps(
                {
                    "schema": RECEIPT_SCHEMA,
                    "status": "EFFECT_UNKNOWN",
                    "retry_allowed": False,
                },
                sort_keys=True,
            )
        )
        return 3
    except (InstallError, credential_file.MosyleCredentialFileError):
        print("mosyle-credential: installation refused", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "schema": RECEIPT_SCHEMA,
                "status": status,
                "credential_path": str(credential_file.CREDENTIAL_PATH),
                "mode": "0600",
                "secret_echoed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
