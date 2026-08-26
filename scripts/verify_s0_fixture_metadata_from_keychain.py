#!/usr/bin/env python3
"""Qualify the fixed MAS-112 Slack fixture credential from the login Keychain.

The credential is read in-process through macOS Security.framework, validated,
and delivered only through the existing metadata verifier's anonymous stdin
pipe. This helper has no caller-selectable credential coordinates and emits
only the verifier receipt schema.
"""
from __future__ import annotations

import ctypes
import json
import os
import pwd
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Sequence, TextIO

_REPO_ROOT = Path(__file__).resolve().parents[1]
_repo_root = str(_REPO_ROOT)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from integrations.slack_agent_dialogue import metadata_verifier as verifier

_KEYCHAIN_SERVICE = b"mastermind-s0-fixture-slack-bot-token"
_KEYCHAIN_ACCOUNT = b"mastermind-s0-fixture-bot"
_LOGIN_KEYCHAIN_RELATIVE = Path("Library") / "Keychains" / "login.keychain-db"
_SECURITY_FRAMEWORK = "/System/Library/Frameworks/Security.framework/Security"
_CORE_FOUNDATION = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
_EXPECTED_TEAM_ID = "T0BRD2AQXQV"
_EXPECTED_BOT_USER_ID = "U0BST4WG996"
_EXPECTED_SCOPES = ("groups:history", "chat:write")
_VERIFIER_SCRIPT = _REPO_ROOT / "scripts" / "verify_slack_agent_dialogue_metadata.py"
_VERIFIER_TIMEOUT_SECONDS = 15.0
_MAX_RECEIPT_BYTES = 4096
_TOKEN_RE = re.compile(rb"\Axoxb-[A-Za-z0-9-]{20,1000}\Z")
_TOKEN_SHAPED_RE = re.compile(rb"(?i)(?:^|[^A-Za-z0-9])xox[abprs]-[A-Za-z0-9-]{10,}")
_BOT_ID_RE = re.compile(r"\AB[A-Z0-9]{8,31}\Z")


class MetadataBridgeRefusal(RuntimeError):
    """One closed refusal expressed using the verifier's existing codes."""

    def __init__(self, code: str) -> None:
        if code not in verifier.ERROR_CODES:
            raise ValueError("unknown metadata-verification error code")
        super().__init__(code)
        self.code = code


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _fixed_error(code: str) -> dict[str, object]:
    if code not in verifier.ERROR_CODES:
        raise ValueError("unknown metadata-verification error code")
    return {"error": code, "schema": verifier.RECEIPT_SCHEMA, "status": "ERROR"}


def _login_keychain_path(
    *,
    uid_fn: Callable[[], int] = os.getuid,
    pwd_lookup: Callable[[int], Any] = pwd.getpwuid,
) -> bytes:
    """Derive the current OS account's login-Keychain path without HOME."""

    try:
        record = pwd_lookup(uid_fn())
        home = record.pw_dir
    except Exception:
        raise MetadataBridgeRefusal("METADATA_INPUT_REFUSED") from None
    if not isinstance(home, str) or not home.startswith("/"):
        raise MetadataBridgeRefusal("METADATA_INPUT_REFUSED")
    return os.fsencode(Path(home) / _LOGIN_KEYCHAIN_RELATIVE)


class _SecurityFramework:
    """Minimal explicit-login-Keychain generic-password reader."""

    def __init__(
        self,
        *,
        loader=ctypes.CDLL,
        login_keychain_path_fn: Callable[[], bytes] = _login_keychain_path,
    ) -> None:
        security = loader(_SECURITY_FRAMEWORK)
        core_foundation = loader(_CORE_FOUNDATION)

        self._open = security.SecKeychainOpen
        self._open.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)]
        self._open.restype = ctypes.c_int32

        self._find = security.SecKeychainFindGenericPassword
        self._find.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_char_p,
            ctypes.c_uint32,
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self._find.restype = ctypes.c_int32

        self._free = security.SecKeychainItemFreeContent
        self._free.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self._free.restype = ctypes.c_int32

        self._release = core_foundation.CFRelease
        self._release.argtypes = [ctypes.c_void_p]
        self._release.restype = None

        path = login_keychain_path_fn()
        if not isinstance(path, bytes) or not path.endswith(b"/Library/Keychains/login.keychain-db"):
            raise MetadataBridgeRefusal("METADATA_INPUT_REFUSED")
        self._login_keychain_path = path

    def read_secret(self) -> bytearray:
        keychain = ctypes.c_void_p()
        status = self._open(self._login_keychain_path, ctypes.byref(keychain))
        if status != 0 or not keychain.value:
            raise MetadataBridgeRefusal("METADATA_INPUT_REFUSED")

        password_length = ctypes.c_uint32()
        password_data = ctypes.c_void_p()
        try:
            status = self._find(
                keychain,
                len(_KEYCHAIN_SERVICE),
                _KEYCHAIN_SERVICE,
                len(_KEYCHAIN_ACCOUNT),
                _KEYCHAIN_ACCOUNT,
                ctypes.byref(password_length),
                ctypes.byref(password_data),
                None,
            )
            length = int(password_length.value)
            if (
                status != 0
                or not password_data.value
                or length <= 0
                or length > verifier.MAX_TOKEN_BYTES
            ):
                raise MetadataBridgeRefusal("METADATA_INPUT_REFUSED")
            secret = bytearray(length)
            target = (ctypes.c_ubyte * length).from_buffer(secret)
            ctypes.memmove(target, password_data, length)
            return secret
        finally:
            if password_data.value:
                try:
                    self._free(None, password_data)
                except Exception:
                    pass
            try:
                self._release(keychain)
            except Exception:
                pass


def _validate_secret(secret: Any) -> bytearray:
    if not isinstance(secret, bytearray):
        raise MetadataBridgeRefusal("METADATA_INPUT_REFUSED")
    if (
        not secret
        or len(secret) > verifier.MAX_TOKEN_BYTES
        or _TOKEN_RE.fullmatch(secret) is None
    ):
        raise MetadataBridgeRefusal("METADATA_INPUT_REFUSED")
    return secret


def _verifier_argv() -> list[str]:
    return [
        sys.executable,
        str(_VERIFIER_SCRIPT),
        "--expected-team-id",
        _EXPECTED_TEAM_ID,
        "--expected-bot-user-id",
        _EXPECTED_BOT_USER_ID,
        "--expected-scope",
        _EXPECTED_SCOPES[0],
        "--expected-scope",
        _EXPECTED_SCOPES[1],
    ]


def _closed_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise MetadataBridgeRefusal("METADATA_RESPONSE_REFUSED")
        result[key] = value
    return result


def _parse_allowlisted_receipt(raw: bytes, *, returncode: int) -> dict[str, object]:
    if (
        not isinstance(raw, bytes)
        or not raw
        or len(raw) > _MAX_RECEIPT_BYTES
        or not raw.endswith(b"\n")
        or raw[:-1].find(b"\n") != -1
    ):
        raise MetadataBridgeRefusal("METADATA_RESPONSE_REFUSED")
    if _TOKEN_SHAPED_RE.search(raw) is not None:
        raise MetadataBridgeRefusal("SECRET_SURFACE_REFUSED")
    try:
        document = json.loads(
            raw[:-1].decode("utf-8"),
            object_pairs_hook=_closed_json_object,
        )
    except MetadataBridgeRefusal:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise MetadataBridgeRefusal("METADATA_RESPONSE_REFUSED") from None
    if not isinstance(document, dict):
        raise MetadataBridgeRefusal("METADATA_RESPONSE_REFUSED")

    status = document.get("status")
    if status == "PASS":
        if returncode != 0 or set(document) != {
            "bot_id",
            "bot_user_id",
            "schema",
            "scopes",
            "status",
            "team_id",
        }:
            raise MetadataBridgeRefusal("METADATA_RESPONSE_REFUSED")
        bot_id = document.get("bot_id")
        if (
            document.get("schema") != verifier.RECEIPT_SCHEMA
            or document.get("team_id") != _EXPECTED_TEAM_ID
            or document.get("bot_user_id") != _EXPECTED_BOT_USER_ID
            or document.get("scopes") != sorted(_EXPECTED_SCOPES)
            or not isinstance(bot_id, str)
            or _BOT_ID_RE.fullmatch(bot_id) is None
        ):
            raise MetadataBridgeRefusal("METADATA_RESPONSE_REFUSED")
        return {
            "bot_id": bot_id,
            "bot_user_id": _EXPECTED_BOT_USER_ID,
            "schema": verifier.RECEIPT_SCHEMA,
            "scopes": sorted(_EXPECTED_SCOPES),
            "status": "PASS",
            "team_id": _EXPECTED_TEAM_ID,
        }

    if status == "ERROR":
        if returncode != 2 or set(document) != {"error", "schema", "status"}:
            raise MetadataBridgeRefusal("METADATA_RESPONSE_REFUSED")
        code = document.get("error")
        if document.get("schema") != verifier.RECEIPT_SCHEMA or code not in verifier.ERROR_CODES:
            raise MetadataBridgeRefusal("METADATA_RESPONSE_REFUSED")
        return _fixed_error(str(code))

    raise MetadataBridgeRefusal("METADATA_RESPONSE_REFUSED")


def _contains_exact_secret(data: bytes, secret: bytearray) -> bool:
    return bool(secret) and data.find(secret) >= 0


def _run_verifier(
    secret: bytearray,
    *,
    runner=subprocess.run,
) -> dict[str, object]:
    argv = _verifier_argv()
    try:
        completed = runner(
            argv,
            input=secret,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={},
            cwd=str(_REPO_ROOT),
            timeout=_VERIFIER_TIMEOUT_SECONDS,
            check=False,
            shell=False,
        )
    except Exception:
        raise MetadataBridgeRefusal("METADATA_RESPONSE_REFUSED") from None

    stdout = completed.stdout
    stderr = completed.stderr
    if not isinstance(stdout, bytes) or not isinstance(stderr, bytes):
        raise MetadataBridgeRefusal("METADATA_RESPONSE_REFUSED")
    if (
        _TOKEN_SHAPED_RE.search(stdout) is not None
        or _TOKEN_SHAPED_RE.search(stderr) is not None
        or _contains_exact_secret(stdout, secret)
        or _contains_exact_secret(stderr, secret)
    ):
        raise MetadataBridgeRefusal("SECRET_SURFACE_REFUSED")
    if stderr:
        raise MetadataBridgeRefusal("METADATA_RESPONSE_REFUSED")
    return _parse_allowlisted_receipt(stdout, returncode=int(completed.returncode))


def _zero_secret(secret: bytearray | None) -> None:
    if isinstance(secret, bytearray):
        secret[:] = b"\x00" * len(secret)


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    api_factory=_SecurityFramework,
    runner=subprocess.run,
) -> int:
    out = stdout if stdout is not None else sys.stdout
    args = list(sys.argv[1:] if argv is None else argv)
    receipt: dict[str, object]
    secret: bytearray | None = None

    if args:
        receipt = _fixed_error("METADATA_ARGUMENTS_REFUSED")
    else:
        try:
            secret = _validate_secret(api_factory().read_secret())
            receipt = _run_verifier(secret, runner=runner)
        except MetadataBridgeRefusal as exc:
            receipt = _fixed_error(exc.code)
        except Exception:
            receipt = _fixed_error("METADATA_RESPONSE_REFUSED")
        finally:
            _zero_secret(secret)
            secret = None

    out.write(_canonical_json(receipt) + "\n")
    return 0 if receipt.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
