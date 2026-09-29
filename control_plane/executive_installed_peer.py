"""Private Darwin dynamic-code observation primitive.

This module obtains a running code object from the exact 32-byte kernel audit
token and checks it against the designated requirement of an expected on-disk
executable. It is a source primitive only: it does not qualify an installed
service, bind an owner, or prove launchd/root/boot/closure.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import sys

from control_plane.executive_peer_identity import PeerIdentityError

__all__ = ["qualify_installed_peer"]

_AUDIT_TOKEN_NBYTES = 32
_MAX_PATH_BYTES = 4096
_MAX_REQUIREMENT_BYTES = 65536
_MAX_UNIQUE_BYTES = 64
_ERR_SEC_SUCCESS = 0

_SECURITY_FRAMEWORK = (
    "/System/Library/Frameworks/Security.framework/Security"
)
_COREFOUNDATION_FRAMEWORK = (
    "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
)

_OSStatus = ctypes.c_int32
_CFIndex = ctypes.c_long
_CFTypeID = ctypes.c_ulong
_Boolean = ctypes.c_ubyte
_SecCSFlags = ctypes.c_uint32
_CFTypeRef = ctypes.c_void_p


@dataclass(frozen=True, slots=True)
class _DynamicCodeObservation:
    """Immutable dynamic-code snapshot. Not authority and not a public record."""

    designated_requirement_digest: str
    dynamic_code_identity_digest: str
    dynamic_code_status: int
    executable_path: str


def qualify_installed_peer(peer, *, role):
    """Public gateway is not armed in this source slice.

    Always fails closed. Does not observe code, bind an owner, or consult A2.
    """
    raise PeerIdentityError("SERVICE_INSTALLATION_QUALIFICATION_INCOMPLETE")


def _observe_dynamic_code(
    audit_token: bytes, expected_executable: str
) -> _DynamicCodeObservation:
    """Map a kernel audit token to a validity-checked dynamic code identity.

    expected_executable is a private topology path, not a public pin override.
    """
    _require_audit_token(audit_token)
    _require_expected_executable(expected_executable)
    api = _darwin_security_api()
    owned: list[int] = []
    try:
        return _observe_with_api(api, audit_token, expected_executable, owned)
    finally:
        for ref in reversed(owned):
            if ref:
                api.CFRelease(ref)


def _require_audit_token(audit_token: object) -> None:
    if type(audit_token) is not bytes or len(audit_token) != _AUDIT_TOKEN_NBYTES:
        raise PeerIdentityError("PEER_AUDIT_TOKEN_INVALID")


def _require_expected_executable(path: object) -> None:
    if (
        type(path) is not str
        or not path.startswith("/")
        or len(path) > _MAX_PATH_BYTES
        or not path.isascii()
        or any(ord(char) < 32 or ord(char) == 127 for char in path)
        or any(part in ("", ".", "..") for part in path.split("/")[1:])
    ):
        raise PeerIdentityError("SERVICE_EXPECTED_EXECUTABLE_INVALID")


class _DarwinSecurityAPI:
    """Bound Security.framework / CoreFoundation entry points."""

    __slots__ = (
        "CFDataCreate",
        "CFDataGetBytePtr",
        "CFDataGetLength",
        "CFDataGetTypeID",
        "CFDictionaryCreate",
        "CFDictionaryGetTypeID",
        "CFDictionaryGetValue",
        "CFGetTypeID",
        "CFRelease",
        "CFURLCreateFromFileSystemRepresentation",
        "CFURLGetFileSystemRepresentation",
        "CFURLGetTypeID",
        "SecCodeCheckValidity",
        "SecCodeCopyDesignatedRequirement",
        "SecCodeCopyGuestWithAttributes",
        "SecCodeCopyPath",
        "SecCodeCopySigningInformation",
        "SecRequirementCopyData",
        "SecStaticCodeCreateWithPath",
        "kCFTypeDictionaryKeyCallBacks",
        "kCFTypeDictionaryValueCallBacks",
        "kSecCodeInfoMainExecutable",
        "kSecCodeInfoUnique",
        "kSecGuestAttributeAudit",
    )


def _symbol(library: object, name: str):
    try:
        return getattr(library, name)
    except AttributeError:
        raise PeerIdentityError("SERVICE_CODE_SIGNING_API_UNAVAILABLE") from None


def _exported_pointer(library: object, name: str) -> int:
    try:
        value = ctypes.c_void_p.in_dll(library, name).value
    except (ValueError, AttributeError, TypeError):
        raise PeerIdentityError("SERVICE_CODE_SIGNING_API_UNAVAILABLE") from None
    if not value:
        raise PeerIdentityError("SERVICE_CODE_SIGNING_API_UNAVAILABLE")
    return value


def _exported_address(library: object, name: str) -> int:
    try:
        return ctypes.addressof(ctypes.c_char.in_dll(library, name))
    except (ValueError, AttributeError, TypeError):
        raise PeerIdentityError("SERVICE_CODE_SIGNING_API_UNAVAILABLE") from None


def _bind_function(library: object, name: str, restype, argtypes):
    function = _symbol(library, name)
    function.restype = restype
    function.argtypes = argtypes
    return function


@lru_cache(maxsize=1)
def _darwin_security_api() -> _DarwinSecurityAPI:
    if sys.platform != "darwin":
        raise PeerIdentityError("PEER_PLATFORM_UNSUPPORTED")
    try:
        security = ctypes.CDLL(_SECURITY_FRAMEWORK)
        core = ctypes.CDLL(_COREFOUNDATION_FRAMEWORK)
    except OSError:
        raise PeerIdentityError("SERVICE_CODE_SIGNING_API_UNAVAILABLE") from None
    api = _DarwinSecurityAPI()
    try:
        api.CFDataCreate = _bind_function(
            core,
            "CFDataCreate",
            _CFTypeRef,
            [_CFTypeRef, ctypes.POINTER(ctypes.c_ubyte), _CFIndex],
        )
        api.CFDataGetLength = _bind_function(
            core, "CFDataGetLength", _CFIndex, [_CFTypeRef]
        )
        api.CFDataGetBytePtr = _bind_function(
            core, "CFDataGetBytePtr", ctypes.c_void_p, [_CFTypeRef]
        )
        api.CFDataGetTypeID = _bind_function(
            core, "CFDataGetTypeID", _CFTypeID, []
        )
        api.CFDictionaryCreate = _bind_function(
            core,
            "CFDictionaryCreate",
            _CFTypeRef,
            [
                _CFTypeRef,
                ctypes.POINTER(ctypes.c_void_p),
                ctypes.POINTER(ctypes.c_void_p),
                _CFIndex,
                ctypes.c_void_p,
                ctypes.c_void_p,
            ],
        )
        api.CFDictionaryGetValue = _bind_function(
            core, "CFDictionaryGetValue", ctypes.c_void_p, [_CFTypeRef, ctypes.c_void_p]
        )
        api.CFDictionaryGetTypeID = _bind_function(
            core, "CFDictionaryGetTypeID", _CFTypeID, []
        )
        api.CFURLCreateFromFileSystemRepresentation = _bind_function(
            core,
            "CFURLCreateFromFileSystemRepresentation",
            _CFTypeRef,
            [_CFTypeRef, ctypes.POINTER(ctypes.c_ubyte), _CFIndex, _Boolean],
        )
        api.CFURLGetFileSystemRepresentation = _bind_function(
            core,
            "CFURLGetFileSystemRepresentation",
            _Boolean,
            [_CFTypeRef, _Boolean, ctypes.POINTER(ctypes.c_ubyte), _CFIndex],
        )
        api.CFURLGetTypeID = _bind_function(
            core, "CFURLGetTypeID", _CFTypeID, []
        )
        api.CFGetTypeID = _bind_function(
            core, "CFGetTypeID", _CFTypeID, [_CFTypeRef]
        )
        api.CFRelease = _bind_function(core, "CFRelease", None, [_CFTypeRef])
        api.SecCodeCopyGuestWithAttributes = _bind_function(
            security,
            "SecCodeCopyGuestWithAttributes",
            _OSStatus,
            [_CFTypeRef, _CFTypeRef, _SecCSFlags, ctypes.POINTER(ctypes.c_void_p)],
        )
        api.SecStaticCodeCreateWithPath = _bind_function(
            security,
            "SecStaticCodeCreateWithPath",
            _OSStatus,
            [_CFTypeRef, _SecCSFlags, ctypes.POINTER(ctypes.c_void_p)],
        )
        api.SecCodeCopyDesignatedRequirement = _bind_function(
            security,
            "SecCodeCopyDesignatedRequirement",
            _OSStatus,
            [_CFTypeRef, _SecCSFlags, ctypes.POINTER(ctypes.c_void_p)],
        )
        api.SecRequirementCopyData = _bind_function(
            security,
            "SecRequirementCopyData",
            _OSStatus,
            [_CFTypeRef, _SecCSFlags, ctypes.POINTER(ctypes.c_void_p)],
        )
        api.SecCodeCheckValidity = _bind_function(
            security,
            "SecCodeCheckValidity",
            _OSStatus,
            [_CFTypeRef, _SecCSFlags, _CFTypeRef],
        )
        # SecCodeCopyPath yields a bundle container for bundled code, so the
        # binding is kept for ABI completeness but never supplies identity.
        api.SecCodeCopyPath = _bind_function(
            security,
            "SecCodeCopyPath",
            _OSStatus,
            [_CFTypeRef, _SecCSFlags, ctypes.POINTER(ctypes.c_void_p)],
        )
        api.SecCodeCopySigningInformation = _bind_function(
            security,
            "SecCodeCopySigningInformation",
            _OSStatus,
            [_CFTypeRef, _SecCSFlags, ctypes.POINTER(ctypes.c_void_p)],
        )
        api.kSecGuestAttributeAudit = _exported_pointer(
            security, "kSecGuestAttributeAudit"
        )
        api.kSecCodeInfoMainExecutable = _exported_pointer(
            security, "kSecCodeInfoMainExecutable"
        )
        api.kSecCodeInfoUnique = _exported_pointer(security, "kSecCodeInfoUnique")
        api.kCFTypeDictionaryKeyCallBacks = _exported_address(
            core, "kCFTypeDictionaryKeyCallBacks"
        )
        api.kCFTypeDictionaryValueCallBacks = _exported_address(
            core, "kCFTypeDictionaryValueCallBacks"
        )
    except PeerIdentityError:
        raise
    except (AttributeError, TypeError, ValueError):
        raise PeerIdentityError("SERVICE_CODE_SIGNING_API_UNAVAILABLE") from None
    return api


def _cfdata_create(api: _DarwinSecurityAPI, blob: bytes) -> int:
    buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    ref = api.CFDataCreate(None, buffer, len(blob))
    if not ref:
        raise PeerIdentityError("SERVICE_CODE_SIGNING_API_UNAVAILABLE")
    return int(ref)


def _cfurl_create(api: _DarwinSecurityAPI, path: str) -> int:
    blob = path.encode("ascii")
    buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    ref = api.CFURLCreateFromFileSystemRepresentation(None, buffer, len(blob), 0)
    if not ref:
        raise PeerIdentityError("SERVICE_STATIC_CODE_UNAVAILABLE")
    return int(ref)


def _owned_copy(function, error: str, *args) -> int:
    output = ctypes.c_void_p()
    status = function(*args, ctypes.byref(output))
    if type(status) is not int or status != _ERR_SEC_SUCCESS or not output.value:
        raise PeerIdentityError(error)
    return int(output.value)


def _copy_cfdata(api: _DarwinSecurityAPI, ref, *, maximum: int, error: str) -> bytes:
    if not ref:
        raise PeerIdentityError(error)
    if api.CFGetTypeID(ref) != api.CFDataGetTypeID():
        raise PeerIdentityError(error)
    length = api.CFDataGetLength(ref)
    if type(length) is not int or length < 1 or length > maximum:
        raise PeerIdentityError(error)
    pointer = api.CFDataGetBytePtr(ref)
    if not pointer:
        raise PeerIdentityError(error)
    blob = ctypes.string_at(pointer, length)
    if type(blob) is not bytes or len(blob) != length:
        raise PeerIdentityError(error)
    return blob


def _decode_file_url(api: _DarwinSecurityAPI, url) -> bytes:
    if not url or api.CFGetTypeID(url) != api.CFURLGetTypeID():
        raise PeerIdentityError("SERVICE_DYNAMIC_CODE_PATH_UNAVAILABLE")
    buffer = (ctypes.c_ubyte * _MAX_PATH_BYTES)()
    ok = api.CFURLGetFileSystemRepresentation(url, 0, buffer, _MAX_PATH_BYTES)
    if type(ok) is not int or ok != 1:
        raise PeerIdentityError("SERVICE_DYNAMIC_CODE_PATH_UNAVAILABLE")
    raw = bytes(buffer)
    if b"\0" not in raw:
        raise PeerIdentityError("SERVICE_DYNAMIC_CODE_PATH_UNAVAILABLE")
    path_bytes = raw.split(b"\0", 1)[0]
    if not path_bytes or len(path_bytes) > _MAX_PATH_BYTES:
        raise PeerIdentityError("SERVICE_DYNAMIC_CODE_PATH_UNAVAILABLE")
    return path_bytes


def _borrowed_main_executable(api: _DarwinSecurityAPI, information) -> bytes:
    """Decode the borrowed main-executable CFURL of an owned information dict.

    SecCodeCopyPath reports a bundle container, not its executable, so it must
    never supply executable identity. The URL here is borrowed: the dictionary
    stays owned by the caller until this value is consumed, and the URL itself
    is never released.
    """
    url = api.CFDictionaryGetValue(information, api.kSecCodeInfoMainExecutable)
    if not url:
        raise PeerIdentityError("SERVICE_CODE_IDENTITY_MALFORMED")
    if api.CFGetTypeID(url) != api.CFURLGetTypeID():
        raise PeerIdentityError("SERVICE_CODE_IDENTITY_MALFORMED")
    return _decode_file_url(api, url)


def _identity_digest(audit_token: bytes, unique: bytes, path_bytes: bytes) -> str:
    hasher = hashlib.sha256()
    for part in (audit_token, unique, path_bytes):
        hasher.update(len(part).to_bytes(8, "big"))
        hasher.update(part)
    return hasher.hexdigest()


def _observe_with_api(
    api: _DarwinSecurityAPI,
    audit_token: bytes,
    expected_executable: str,
    owned: list[int],
) -> _DynamicCodeObservation:
    audit_data = _cfdata_create(api, audit_token)
    owned.append(audit_data)
    keys = (ctypes.c_void_p * 1)(api.kSecGuestAttributeAudit)
    values = (ctypes.c_void_p * 1)(audit_data)
    attributes = api.CFDictionaryCreate(
        None,
        keys,
        values,
        1,
        api.kCFTypeDictionaryKeyCallBacks,
        api.kCFTypeDictionaryValueCallBacks,
    )
    if not attributes:
        raise PeerIdentityError("SERVICE_DYNAMIC_GUEST_UNAVAILABLE")
    owned.append(int(attributes))
    guest = _owned_copy(
        api.SecCodeCopyGuestWithAttributes,
        "SERVICE_DYNAMIC_GUEST_UNAVAILABLE",
        None,
        attributes,
        0,
    )
    owned.append(guest)
    expected_url = _cfurl_create(api, expected_executable)
    owned.append(expected_url)
    static_code = _owned_copy(
        api.SecStaticCodeCreateWithPath,
        "SERVICE_STATIC_CODE_UNAVAILABLE",
        expected_url,
        0,
    )
    owned.append(static_code)
    requirement = _owned_copy(
        api.SecCodeCopyDesignatedRequirement,
        "SERVICE_DESIGNATED_REQUIREMENT_UNAVAILABLE",
        static_code,
        0,
    )
    owned.append(requirement)
    requirement_data = _owned_copy(
        api.SecRequirementCopyData,
        "SERVICE_DESIGNATED_REQUIREMENT_UNAVAILABLE",
        requirement,
        0,
    )
    owned.append(requirement_data)
    requirement_blob = _copy_cfdata(
        api,
        requirement_data,
        maximum=_MAX_REQUIREMENT_BYTES,
        error="SERVICE_DESIGNATED_REQUIREMENT_UNAVAILABLE",
    )
    validity = api.SecCodeCheckValidity(guest, 0, requirement)
    if type(validity) is not int or validity != _ERR_SEC_SUCCESS:
        raise PeerIdentityError("SERVICE_DYNAMIC_CODE_NOT_VALID")
    information = _owned_copy(
        api.SecCodeCopySigningInformation,
        "SERVICE_CODE_IDENTITY_UNAVAILABLE",
        guest,
        0,
    )
    owned.append(information)
    if api.CFGetTypeID(information) != api.CFDictionaryGetTypeID():
        raise PeerIdentityError("SERVICE_CODE_IDENTITY_MALFORMED")
    path_bytes = _borrowed_main_executable(api, information)
    try:
        actual_path = path_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise PeerIdentityError("SERVICE_DYNAMIC_CODE_PATH_UNAVAILABLE") from None
    if actual_path != expected_executable:
        raise PeerIdentityError("SERVICE_EXECUTABLE_PATH_MISMATCH")
    unique_ref = api.CFDictionaryGetValue(information, api.kSecCodeInfoUnique)
    unique = _copy_cfdata(
        api,
        unique_ref,
        maximum=_MAX_UNIQUE_BYTES,
        error="SERVICE_CODE_IDENTITY_MALFORMED",
    )
    return _DynamicCodeObservation(
        designated_requirement_digest=hashlib.sha256(requirement_blob).hexdigest(),
        dynamic_code_identity_digest=_identity_digest(audit_token, unique, path_bytes),
        dynamic_code_status=0,
        executable_path=actual_path,
    )
