#!/usr/bin/env python3
"""Read the fixed MAS-112 Slack fixture credential and run its safe verifier.

The secret boundary is intentionally narrow:

* the macOS login Keychain is opened by its fixed user-keychain path;
* the fixed generic-password service/account are read in-process with
  Security.framework;
* only a validated ``xoxb-...`` byte buffer crosses an anonymous stdin pipe to
  the existing metadata verifier; and
* this process emits only a closed, non-secret metadata receipt.

No caller-selectable credential coordinate, secret argv/environment carrier,
shell, temporary file, log, or alternate Keychain search path exists here.
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
from typing import Mapping, Sequence, TextIO

_KEYCHAIN_SERVICE = b"mastermind-s0-fixture-slack-bot-token"
_KEYCHAIN_ACCOUNT = b"mastermind-s0-fixture-bot"
_EXPECTED_TEAM_ID = "T0BRD2AQXQV"
_EXPECTED_BOT_USER_ID = "U0BST4WG996"
_EXPECTED_SCOPES = ("chat:write", "groups:history")

_SECURITY_FRAMEWORK = "/System/Library/Frameworks/Security.framework/Security"
_CORE_FOUNDATION = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
_LOGIN_KEYCHAIN_SUFFIX = "Library/Keychains/login.keychain-db"

_RECEIPT_SCHEMA = "mastermind.slack_agent_dialogue.metadata_verification.v1"
_MAX_TOKEN_BYTES = 1024
_MAX_RECEIPT_BYTES = 4096
_VERIFIER_TIMEOUT_SECONDS = 15.0

_TOKEN_RE = re.compile(rb"\Axoxb-[A-Za-z0-9-]{20,1000}\Z")
_TOKEN_SHAPED_RE = re.compile(rb"(?i)(?:^|[^A-Za-z0-9])xox[abprs]-[A-Za-z0-9-]{10,}")
_BOT_ID_RE = re.compile(r"\AB[A-Z0-9]{8,31}\Z")
_ALLOWED_ERROR_CODES = frozenset(
    {
        "METADATA_ARGUMENTS_REFUSED",
        "METADATA_EXPECTATION_REFUSED",
        "METADATA_IDENTITY_MISMATCH",
        "METADATA_INPUT_REFUSED",
        "METADATA_RESPONSE_REFUSED",
        "METADATA_SCOPE_MISMATCH",
        "SECRET_SURFACE_REFUSED",
        "SLACK_AUTH_REFUSED",
        "SLACK_AUTH_UNAVAILABLE",
    }
)


class _BridgeRefusal(Exception):
    """One opaque helper-side refusal; exception details never cross output."""

    def __init__(self, code: str) -> None:
        if code not in _ALLOWED_ERROR_CODES:
            raise ValueError("unknown MAS-112 bridge refusal")
        super().__init__(code)
        self.code = code


def _default_home_lookup() -> str:
    """Resolve the invoking principal's real home without consulting HOME."""

    return pwd.getpwuid(os.getuid()).pw_dir


class _SecurityFramework:
    """Minimal, explicit-login-Keychain generic-password reader."""

    def __init__(self, *, loader=ctypes.CDLL, home_lookup=_default_home_lookup) -> None:
        security = loader(_SECURITY_FRAMEWORK)
        core_foundation = loader(_CORE_FOUNDATION)

        self._keychain_open = security.SecKeychainOpen
        self._keychain_open.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)]
        self._keychain_open.restype = ctypes.c_int32

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

        self._free_content = security.SecKeychainItemFreeContent
        self._free_content.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self._free_content.restype = ctypes.c_int32

        self._release = core_foundation.CFRelease
        self._release.argtypes = [ctypes.c_void_p]
        self._release.restype = None

        home = home_lookup()
        if not isinstance(home, str) or not home.startswith("/"):
            raise _BridgeRefusal("METADATA_INPUT_REFUSED")
        self._login_keychain_path = f"{home.rstrip('/')}/{_LOGIN_KEYCHAIN_SUFFIX}".encode(
            "utf-8", errors="strict"
        )

    def read_secret(self) -> bytearray:
        """Read only the fixed item from the explicitly opened login Keychain."""

        keychain = ctypes.c_void_p()
        password_data = ctypes.c_void_p()
        password_length = ctypes.c_uint32()
        opened = False
        content_owned = False
        try:
            status = self._keychain_open(self._login_keychain_path, ctypes.byref(keychain))
            if status != 0 or not keychain.value:
                raise _BridgeRefusal("METADATA_INPUT_REFUSED")
            opened = True

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
            if status != 0 or not password_data.value:
                raise _BridgeRefusal("METADATA_INPUT_REFUSED")
            content_owned = True

            length = int(password_length.value)
            if length <= 0 or length > _MAX_TOKEN_BYTES:
                raise _BridgeRefusal("METADATA_INPUT_REFUSED")

            secret = bytearray(length)
            destination = (ctypes.c_ubyte * length).from_buffer(secret)
            ctypes.memmove(destination, password_data, length)
            del destination
            return secret
        except _BridgeRefusal:
            raise
        except Exception:
            raise _BridgeRefusal("METADATA_INPUT_REFUSED") from None
        finally:
            if content_owned:
                try:
                    self._free_content(None, password_data)
                except Exception:
                    pass
            if opened:
                try:
                    self._release(keychain)
                except Exception:
                    pass


def _canonical_json(document: Mapping[str, object]) -> str:
    return json.dumps(
        dict(document),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _error_document(code: str) -> dict[str, object]:
    if code not in _ALLOWED_ERROR_CODES:
        code = "METADATA_RESPONSE_REFUSED"
    return {"error": code, "schema": _RECEIPT_SCHEMA, "status": "ERROR"}


def _validate_secret(secret: bytearray) -> None:
    if not secret or len(secret) > _MAX_TOKEN_BYTES or _TOKEN_RE.fullmatch(secret) is None:
        raise _BridgeRefusal("METADATA_INPUT_REFUSED")


def _run_verifier(secret: bytearray, *, popen_factory=subprocess.Popen):
    verifier = Path(__file__).resolve().with_name("verify_slack_agent_dialogue_metadata.py")
    argv = [
        sys.executable,
        str(verifier),
        "--expected-team-id",
        _EXPECTED_TEAM_ID,
        "--expected-bot-user-id",
        _EXPECTED_BOT_USER_ID,
        "--expected-scope",
        _EXPECTED_SCOPES[0],
        "--expected-scope",
        _EXPECTED_SCOPES[1],
    ]
    try:
        process = popen_factory(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={},
            close_fds=True,
        )
        try:
            child_stdout, child_stderr = process.communicate(
                input=secret,
                timeout=_VERIFIER_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise _BridgeRefusal("METADATA_RESPONSE_REFUSED") from None
    except _BridgeRefusal:
        raise
    except Exception:
        raise _BridgeRefusal("METADATA_RESPONSE_REFUSED") from None

    return int(process.returncode), bytes(child_stdout), bytes(child_stderr)


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise _BridgeRefusal("METADATA_RESPONSE_REFUSED")
        document[key] = value
    return document


def _parse_child_receipt(
    returncode: int,
    child_stdout: bytes,
    child_stderr: bytes,
) -> tuple[int, dict[str, object]]:
    if _TOKEN_SHAPED_RE.search(child_stdout) or _TOKEN_SHAPED_RE.search(child_stderr):
        raise _BridgeRefusal("SECRET_SURFACE_REFUSED")
    if child_stderr:
        raise _BridgeRefusal("METADATA_RESPONSE_REFUSED")
    if not child_stdout or len(child_stdout) > _MAX_RECEIPT_BYTES:
        raise _BridgeRefusal("METADATA_RESPONSE_REFUSED")
    if child_stdout.count(b"\n") != 1 or not child_stdout.endswith(b"\n"):
        raise _BridgeRefusal("METADATA_RESPONSE_REFUSED")

    try:
        document = json.loads(
            child_stdout.decode("utf-8", errors="strict"),
            object_pairs_hook=_closed_object,
        )
    except _BridgeRefusal:
        raise
    except Exception:
        raise _BridgeRefusal("METADATA_RESPONSE_REFUSED") from None
    if not isinstance(document, dict):
        raise _BridgeRefusal("METADATA_RESPONSE_REFUSED")

    if document.get("schema") != _RECEIPT_SCHEMA:
        raise _BridgeRefusal("METADATA_RESPONSE_REFUSED")

    if document.get("status") == "PASS":
        required = {"bot_id", "bot_user_id", "schema", "scopes", "status", "team_id"}
        if returncode != 0 or set(document) != required:
            raise _BridgeRefusal("METADATA_RESPONSE_REFUSED")
        if document.get("team_id") != _EXPECTED_TEAM_ID:
            raise _BridgeRefusal("METADATA_IDENTITY_MISMATCH")
        if document.get("bot_user_id") != _EXPECTED_BOT_USER_ID:
            raise _BridgeRefusal("METADATA_IDENTITY_MISMATCH")
        if document.get("scopes") != list(_EXPECTED_SCOPES):
            raise _BridgeRefusal("METADATA_SCOPE_MISMATCH")
        bot_id = document.get("bot_id")
        if not isinstance(bot_id, str) or _BOT_ID_RE.fullmatch(bot_id) is None:
            raise _BridgeRefusal("METADATA_RESPONSE_REFUSED")
        return 0, document

    if document.get("status") == "ERROR":
        required = {"error", "schema", "status"}
        code = document.get("error")
        if (
            returncode != 2
            or set(document) != required
            or not isinstance(code, str)
            or code not in _ALLOWED_ERROR_CODES
        ):
            raise _BridgeRefusal("METADATA_RESPONSE_REFUSED")
        return 2, document

    raise _BridgeRefusal("METADATA_RESPONSE_REFUSED")


def _zero_secret(secret: bytearray | None) -> None:
    if secret is None:
        return
    for index in range(len(secret)):
        secret[index] = 0


def run(
    argv: Sequence[str],
    *,
    stdout: TextIO | None = None,
    api_factory=_SecurityFramework,
    verifier_runner=_run_verifier,
) -> int:
    out = stdout if stdout is not None else sys.stdout
    secret: bytearray | None = None
    try:
        if argv:
            raise _BridgeRefusal("METADATA_ARGUMENTS_REFUSED")
        secret = api_factory().read_secret()
        if not isinstance(secret, bytearray):
            raise _BridgeRefusal("METADATA_INPUT_REFUSED")
        _validate_secret(secret)
        returncode, child_stdout, child_stderr = verifier_runner(secret)
        visible_returncode, receipt = _parse_child_receipt(
            int(returncode), bytes(child_stdout), bytes(child_stderr)
        )
        out.write(_canonical_json(receipt) + "\n")
        return visible_returncode
    except _BridgeRefusal as exc:
        out.write(_canonical_json(_error_document(exc.code)) + "\n")
        return 2
    except Exception:
        out.write(_canonical_json(_error_document("METADATA_RESPONSE_REFUSED")) + "\n")
        return 2
    finally:
        _zero_secret(secret)


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
