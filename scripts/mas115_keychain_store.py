"""Secret-owning Multilogin Keychain enrollment helper for MAS-115.

This process owns one narrow job: read one current Multilogin access token from
an echo-disabled terminal prompt and write it to the fixed MAS-115 generic-
password item through macOS Security.framework.  The raw value never enters
the parent setup process, argv, environment, stdout, a temporary file, a shell
variable, a log, or a receipt.

The dedicated helper is necessary because ``security add-generic-password -w``
uses a 128-byte interactive input buffer on the Chairman host, while the
current Multilogin access token is a substantially longer JWT.  This helper
does not expose a generic credential service or accept caller-selected
Keychain coordinates.
"""
from __future__ import annotations

import ctypes
import getpass
import re
import sys


_KEYCHAIN_SERVICE = b"mastermind.mas115.multilogin.disposable"
_KEYCHAIN_ACCOUNT = b"mastermind-mas115-canary"
_SECURITY_FRAMEWORK = "/System/Library/Frameworks/Security.framework/Security"
_CORE_FOUNDATION = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
_ERR_SEC_ITEM_NOT_FOUND = -25300
_MIN_SECRET_BYTES = 129
_MAX_SECRET_BYTES = 16 * 1024
_JWT_RE = re.compile(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\Z")


class CredentialStoreRefusal(Exception):
    """Closed, non-secret enrollment refusal."""


class _SecurityFramework:
    """Minimal legacy Keychain adapter with fixed generic-password fields."""

    def __init__(self, *, loader=ctypes.CDLL):
        security = loader(_SECURITY_FRAMEWORK)
        core_foundation = loader(_CORE_FOUNDATION)

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

        self._add = security.SecKeychainAddGenericPassword
        self._add.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_char_p,
            ctypes.c_uint32,
            ctypes.c_char_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self._add.restype = ctypes.c_int32

        self._modify = security.SecKeychainItemModifyAttributesAndData
        self._modify.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        self._modify.restype = ctypes.c_int32

        self._release = core_foundation.CFRelease
        self._release.argtypes = [ctypes.c_void_p]
        self._release.restype = None

    def find_item(self):
        item = ctypes.c_void_p()
        status = self._find(
            None,
            len(_KEYCHAIN_SERVICE),
            _KEYCHAIN_SERVICE,
            len(_KEYCHAIN_ACCOUNT),
            _KEYCHAIN_ACCOUNT,
            None,
            None,
            ctypes.byref(item),
        )
        if status == _ERR_SEC_ITEM_NOT_FOUND:
            return None
        if status != 0 or not item.value:
            raise CredentialStoreRefusal("credential could not be stored")
        return item

    @staticmethod
    def _secret_pointer(secret: bytes):
        buffer = ctypes.create_string_buffer(secret)
        return buffer, ctypes.cast(buffer, ctypes.c_void_p)

    def add_item(self, secret: bytes) -> None:
        buffer, pointer = self._secret_pointer(secret)
        status = self._add(
            None,
            len(_KEYCHAIN_SERVICE),
            _KEYCHAIN_SERVICE,
            len(_KEYCHAIN_ACCOUNT),
            _KEYCHAIN_ACCOUNT,
            len(secret),
            pointer,
            None,
        )
        del buffer
        if status != 0:
            raise CredentialStoreRefusal("credential could not be stored")

    def modify_item(self, item, secret: bytes) -> None:
        buffer, pointer = self._secret_pointer(secret)
        status = self._modify(item, None, len(secret), pointer)
        del buffer
        if status != 0:
            raise CredentialStoreRefusal("credential could not be stored")

    def release_item(self, item) -> None:
        self._release(item)


def _validated_secret(prompt_fn=getpass.getpass) -> bytes:
    value = prompt_fn(
        "Paste the current short-lived Multilogin access token "
        "(input is hidden), then press Return: "
    )
    if not isinstance(value, str) or value != value.strip():
        raise CredentialStoreRefusal("credential is missing or malformed")
    try:
        encoded = value.encode("ascii", errors="strict")
    except UnicodeEncodeError:
        raise CredentialStoreRefusal("credential is missing or malformed") from None
    if (
        len(encoded) < _MIN_SECRET_BYTES
        or len(encoded) > _MAX_SECRET_BYTES
        or _JWT_RE.fullmatch(value) is None
    ):
        raise CredentialStoreRefusal("credential is missing or malformed")
    return encoded


def _store_secret(secret: bytes, api) -> None:
    item = api.find_item()
    if item is None:
        api.add_item(secret)
        return
    try:
        api.modify_item(item, secret)
    finally:
        api.release_item(item)


def main(*, prompt_fn=getpass.getpass, api_factory=_SecurityFramework, stdout=None, stderr=None) -> int:
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    try:
        secret = _validated_secret(prompt_fn)
        _store_secret(secret, api_factory())
    except (CredentialStoreRefusal, KeyboardInterrupt, EOFError):
        print("REFUSED: Multilogin credential was not stored.", file=err)
        return 2
    except Exception:  # noqa: BLE001 — dynamic framework errors stay outside the result boundary
        print("REFUSED: Multilogin credential was not stored.", file=err)
        return 2
    print("Multilogin disposable-canary credential stored in Keychain.", file=out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
