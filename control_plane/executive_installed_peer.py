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
import os
import re
import selectors
import subprocess
import sys
import time

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


# ---------------------------------------------------------------------------
# Appended private launchd observation slice.
#
# Everything above this marker is the frozen R5 dynamic-code primitive and is
# byte-for-byte unchanged. The helpers below are internal building blocks for a
# later complete installed-service factory: they observe launchd's own account
# of one closed system service and the real kernel boot-session UUID. They do
# not qualify an installation, pin release files, bind an owner, or arm the
# public gateway.
# ---------------------------------------------------------------------------

_LAUNCHD_MAX_BYTES = 65536
_LAUNCHD_MAX_LINES = 1024
_LAUNCHD_MAX_LINE_BYTES = 4096
_LAUNCHD_MAX_DEPTH = 8
_LAUNCHD_MAX_ARGV = 64
_LAUNCHD_MAX_COMMAND_BYTES = 65536
_LAUNCHD_MAX_KERNEL_BYTES = 128
_LAUNCHD_MAX_BOOT_ID_BYTES = 128
_LAUNCHD_TIMEOUT_SECONDS = 3.0
_LAUNCHD_POLL_SECONDS = 0.05
_LAUNCHD_READ_CHUNK_BYTES = 4096
_LAUNCHD_REAP_GRACE_SECONDS = 0.5
_LAUNCHD_REQUIRED_TOTAL = 12

_LAUNCHD_ENVIRONMENT = {
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
}

_LAUNCHD_KEY_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ()_.\-/]{0,63}")
_LAUNCHD_PID_PATTERN = re.compile(r"[1-9][0-9]{0,9}")
_LAUNCHD_KERNEL_PATTERN = re.compile(r"25\.5(?:\.[0-9]{1,4}){0,3}")
_LAUNCHD_UUID_PATTERN = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")

_SYSCTL_OSRELEASE_ARGV = ("/usr/sbin/sysctl", "-n", "kern.osrelease")
_SYSCTL_BOOT_ID_ARGV = ("/usr/sbin/sysctl", "-n", "kern.bootsessionuuid")


@dataclass(frozen=True, slots=True)
class _LaunchdRoleSpec:
    """Closed nonsecret launchd profile for exactly one qualified role."""

    label: str
    root: str
    plist_path: str
    username: str
    group: str
    launchctl_argv: tuple


@dataclass(frozen=True, slots=True)
class _LaunchdObservation:
    """Immutable direct-root launchd facts. Not authority and not a public view."""

    service_label: str
    plist_path: str
    state: str
    program: str
    argv: tuple
    working_directory: str
    username: str
    group: str
    pid: int


_LAUNCHD_ROLES = {
    "control": _LaunchdRoleSpec(
        label="com.mastermind.executive.control",
        root="system/com.mastermind.executive.control",
        plist_path=(
            "/Library/LaunchDaemons/com.mastermind.executive.control.plist"
        ),
        username="_mastermind_exec",
        group="_mastermind_exec",
        launchctl_argv=(
            "/bin/launchctl",
            "print",
            "system/com.mastermind.executive.control",
        ),
    ),
    "gateway": _LaunchdRoleSpec(
        label="com.mastermind.executive.mcp",
        root="system/com.mastermind.executive.mcp",
        plist_path="/Library/LaunchDaemons/com.mastermind.executive.mcp.plist",
        username="_mastermind_executive_mcp",
        group="_mastermind_executive_mcp",
        launchctl_argv=(
            "/bin/launchctl",
            "print",
            "system/com.mastermind.executive.mcp",
        ),
    ),
}

_BOUNDED_COMMANDS = (
    _LAUNCHD_ROLES["control"].launchctl_argv,
    _LAUNCHD_ROLES["gateway"].launchctl_argv,
    _SYSCTL_OSRELEASE_ARGV,
    _SYSCTL_BOOT_ID_ARGV,
)

_LAUNCHD_REQUIRED_VALUE_KEYS = frozenset(
    {
        "domain",
        "group",
        "path",
        "pid",
        "program",
        "state",
        "type",
        "username",
        "working directory",
    }
)


def _launchd_refusal(code: str) -> PeerIdentityError:
    """Build a bounded failure. Only a closed code is ever carried outward."""
    return PeerIdentityError(code)


def _launchd_role_spec(role: object) -> _LaunchdRoleSpec:
    spec = _LAUNCHD_ROLES.get(role) if type(role) is str else None
    if spec is None:
        raise _launchd_refusal("SERVICE_LAUNCHD_ROLE_INVALID")
    return spec


def _launchd_is_safe_text(value: object) -> bool:
    """True for one bounded printable-ASCII line body without control bytes."""
    return (
        type(value) is str
        and 1 <= len(value) <= _LAUNCHD_MAX_LINE_BYTES
        and value.isascii()
        and not any(ord(char) < 32 or ord(char) > 126 for char in value)
    )


def _launchd_lines(raw: object) -> list:
    """Split untrusted launchd text into bounded, type-checked logical lines."""
    if type(raw) is not bytes or not raw or len(raw) > _LAUNCHD_MAX_BYTES:
        raise _launchd_refusal("SERVICE_LAUNCHD_RAW_INVALID")
    if b"\r" in raw or not raw.isascii():
        raise _launchd_refusal("SERVICE_LAUNCHD_RAW_INVALID")
    text = raw.decode("ascii")
    if text.endswith("\n"):
        text = text[:-1]
    if not text or text.endswith("\n"):
        raise _launchd_refusal("SERVICE_LAUNCHD_RAW_INVALID")
    lines = text.split("\n")
    if len(lines) > _LAUNCHD_MAX_LINES:
        raise _launchd_refusal("SERVICE_LAUNCHD_LINE_LIMIT")
    for line in lines:
        if len(line) > _LAUNCHD_MAX_LINE_BYTES:
            raise _launchd_refusal("SERVICE_LAUNCHD_LINE_TOO_LARGE")
    return lines


def _launchd_indent(line: str) -> tuple:
    depth = len(line) - len(line.lstrip("\t"))
    return depth, line[depth:]


def _parse_launchctl_service(raw: bytes, *, role: str) -> _LaunchdObservation:
    """Extract only stable direct-root facts from one launchd service print.

    raw is untrusted launchd text. Structure is authoritative: the root header,
    brace balance, one-tab-per-level indentation, and every required direct-root
    field must match the closed profile for role. Volatile direct-root fields
    and nested diagnostic blocks are ignored, and a nested pid, path, type, or
    state can never satisfy a missing root field.
    """
    spec = _launchd_role_spec(role)
    lines = _launchd_lines(raw)
    fields: dict = {}
    seen: dict = {}
    argv: list = []
    arguments_closed = False
    stack: list = []
    root_closed = False

    for index, line in enumerate(lines):
        depth, body = _launchd_indent(line)
        if depth > _LAUNCHD_MAX_DEPTH:
            raise _launchd_refusal("SERVICE_LAUNCHD_OUTPUT_MALFORMED")
        if body == "":
            if not stack or root_closed:
                raise _launchd_refusal("SERVICE_LAUNCHD_OUTPUT_MALFORMED")
            continue
        if body[:1] == " " or not _launchd_is_safe_text(body):
            raise _launchd_refusal("SERVICE_LAUNCHD_OUTPUT_MALFORMED")
        if index == 0:
            if depth != 0 or body != spec.root + " = {":
                raise _launchd_refusal("SERVICE_LAUNCHD_LABEL_MISMATCH")
            stack.append((0, False))
            seen[spec.root] = "block"
            continue
        if root_closed:
            raise _launchd_refusal("SERVICE_LAUNCHD_OUTPUT_TRAILER")
        if body == "}":
            if not stack or depth != stack[-1][0]:
                raise _launchd_refusal("SERVICE_LAUNCHD_OUTPUT_MALFORMED")
            _, is_arguments = stack.pop()
            if is_arguments:
                if not argv:
                    raise _launchd_refusal("SERVICE_LAUNCHD_ARGV_MISSING")
                arguments_closed = True
            if not stack:
                root_closed = True
            continue
        if not stack or depth != stack[-1][0] + 1:
            raise _launchd_refusal("SERVICE_LAUNCHD_OUTPUT_MALFORMED")
        if stack[-1][1]:
            if (
                body.endswith(" = {")
                or body == "{"
                or " = " in body
                or " => " in body
                or body != body.strip(" ")
            ):
                raise _launchd_refusal("SERVICE_LAUNCHD_ARGUMENT_MALFORMED")
            if len(argv) >= _LAUNCHD_MAX_ARGV:
                raise _launchd_refusal("SERVICE_LAUNCHD_ARGV_TOO_LARGE")
            argv.append(body)
            continue
        opener = body.endswith(" = {")
        if depth != 1:
            # Nested diagnostic blocks still participate in brace/depth
            # validation. None of their values can populate root identity.
            if opener:
                if depth >= _LAUNCHD_MAX_DEPTH:
                    raise _launchd_refusal("SERVICE_LAUNCHD_OUTPUT_MALFORMED")
                stack.append((depth, False))
            elif "{" in body or "}" in body:
                raise _launchd_refusal("SERVICE_LAUNCHD_OUTPUT_MALFORMED")
            continue
        key = body[:-4] if opener else body.partition(" = ")[0]
        if not _LAUNCHD_KEY_PATTERN.fullmatch(key):
            raise _launchd_refusal("SERVICE_LAUNCHD_OUTPUT_MALFORMED")
        if key in seen:
            raise _launchd_refusal("SERVICE_LAUNCHD_DUPLICATE_FIELD")
        if opener:
            seen[key] = "block"
            stack.append((depth, key == "arguments"))
            continue
        _, separator, value = body.partition(" = ")
        if not separator or not _launchd_is_safe_text(value) or value != value.strip(
            " "
        ):
            raise _launchd_refusal("SERVICE_LAUNCHD_OUTPUT_MALFORMED")
        seen[key] = "value"
        fields[key] = value

    if stack or not root_closed:
        raise _launchd_refusal("SERVICE_LAUNCHD_OUTPUT_MALFORMED")
    if not arguments_closed or len(argv) < 1:
        raise _launchd_refusal("SERVICE_LAUNCHD_FIELD_MISSING")
    if not _LAUNCHD_REQUIRED_VALUE_KEYS <= set(fields):
        raise _launchd_refusal("SERVICE_LAUNCHD_FIELD_MISSING")
    if fields["path"] != spec.plist_path:
        raise _launchd_refusal("SERVICE_LAUNCHD_PLIST_MISMATCH")
    if fields["type"] != "LaunchDaemon":
        raise _launchd_refusal("SERVICE_LAUNCHD_TYPE_UNQUALIFIED")
    if fields["state"] != "running":
        raise _launchd_refusal("SERVICE_LAUNCHD_STATE_UNQUALIFIED")
    if fields["domain"] != "system":
        raise _launchd_refusal("SERVICE_LAUNCHD_DOMAIN_UNQUALIFIED")
    if fields["username"] != spec.username or fields["group"] != spec.group:
        raise _launchd_refusal("SERVICE_LAUNCHD_IDENTITY_MISMATCH")
    pid_text = fields["pid"]
    if not _LAUNCHD_PID_PATTERN.fullmatch(pid_text) or int(pid_text) > 2147483647:
        raise _launchd_refusal("SERVICE_LAUNCHD_PID_MALFORMED")
    program = fields["program"]
    if program != argv[0]:
        raise _launchd_refusal("SERVICE_LAUNCHD_PROGRAM_MISMATCH")
    return _LaunchdObservation(
        service_label=spec.label,
        plist_path=fields["path"],
        state=fields["state"],
        program=program,
        argv=tuple(argv),
        working_directory=fields["working directory"],
        username=fields["username"],
        group=fields["group"],
        pid=int(pid_text),
    )


def _reap_bounded_exit_code(process, deadline: float):
    """Return a finished child's exit status, or None once the deadline passed."""
    while True:
        try:
            code = process.poll()
        except Exception:
            raise _launchd_refusal("SERVICE_LAUNCHCTL_COMMAND_FAILED") from None
        if type(code) is int:
            return code
        if time.monotonic() >= deadline:
            return None
        try:
            time.sleep(_LAUNCHD_POLL_SECONDS)
        except Exception:
            raise _launchd_refusal("SERVICE_LAUNCHCTL_COMMAND_FAILED") from None


def _discard_bounded_child(process) -> bool:
    """Kill, reap, and release every descriptor of an owned bounded child."""
    try:
        if process.poll() is None:
            process.kill()
    except Exception:
        pass
    stream = getattr(process, "stdout", None)
    if stream is not None:
        try:
            stream.close()
        except Exception:
            pass
    try:
        process.wait(timeout=_LAUNCHD_REAP_GRACE_SECONDS)
    except Exception:
        return False
    return True


def _run_bounded(argv: object, *, max_bytes: object) -> bytes:
    """Run one fixed internal argv with bounded reads and a monotonic deadline.

    Only the closed absolute-path command tuples below are ever executable: no
    caller path, no shell, no inherited environment, no unbounded capture. The
    child is killed, reaped, and its descriptors closed on every outcome.
    """
    if type(argv) is not tuple or argv not in _BOUNDED_COMMANDS:
        raise _launchd_refusal("SERVICE_LAUNCHCTL_COMMAND_NOT_ALLOWED")
    if (
        type(max_bytes) is not int
        or max_bytes < 1
        or max_bytes > _LAUNCHD_MAX_COMMAND_BYTES
    ):
        raise _launchd_refusal("SERVICE_LAUNCHCTL_COMMAND_NOT_ALLOWED")
    if sys.platform != "darwin":
        raise _launchd_refusal("PEER_PLATFORM_UNSUPPORTED")
    deadline = time.monotonic() + _LAUNCHD_TIMEOUT_SECONDS
    try:
        process = subprocess.Popen(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd="/",
            env=dict(_LAUNCHD_ENVIRONMENT),
        )
    except Exception:
        raise _launchd_refusal("SERVICE_LAUNCHCTL_COMMAND_FAILED") from None

    chunks: list = []
    consumed = 0
    payload = b""
    refusal = ""
    try:
        try:
            stream = process.stdout
            if stream is None:
                raise _launchd_refusal("SERVICE_LAUNCHCTL_COMMAND_FAILED")
            descriptor = stream.fileno()
            os.set_blocking(descriptor, False)
            with selectors.DefaultSelector() as selector:
                selector.register(descriptor, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        refusal = "SERVICE_LAUNCHCTL_TIMEOUT"
                        break
                    budget = max_bytes + 1 - consumed
                    if budget <= 0:
                        refusal = "SERVICE_LAUNCHCTL_OUTPUT_TOO_LARGE"
                        break
                    if not selector.select(
                        remaining if remaining < _LAUNCHD_POLL_SECONDS else _LAUNCHD_POLL_SECONDS
                    ):
                        continue
                    try:
                        chunk = os.read(
                            descriptor, min(_LAUNCHD_READ_CHUNK_BYTES, budget)
                        )
                    except BlockingIOError:
                        continue
                    if not chunk:
                        break
                    consumed += len(chunk)
                    chunks.append(chunk)
                    if consumed > max_bytes:
                        refusal = "SERVICE_LAUNCHCTL_OUTPUT_TOO_LARGE"
                        break
            if not refusal:
                code = _reap_bounded_exit_code(process, deadline)
                if code is None:
                    refusal = "SERVICE_LAUNCHCTL_TIMEOUT"
                elif code != 0:
                    refusal = "SERVICE_LAUNCHCTL_COMMAND_FAILED"
                else:
                    payload = b"".join(chunks)
                    if not payload or len(payload) > max_bytes:
                        refusal = "SERVICE_LAUNCHCTL_OUTPUT_TOO_LARGE"
        except PeerIdentityError as error:
            refusal = error.code or "SERVICE_LAUNCHCTL_COMMAND_FAILED"
        except Exception:
            if not refusal:
                refusal = "SERVICE_LAUNCHCTL_COMMAND_FAILED"
    finally:
        if not _discard_bounded_child(process):
            refusal = "SERVICE_LAUNCHCTL_CLEANUP_UNPROVEN"
    if refusal:
        raise _launchd_refusal(refusal)
    return payload


def _bounded_single_line(raw: object, *, maximum: int, code: str) -> str:
    """Return one canonical printable-ASCII line or refuse with a closed code."""
    if (
        type(raw) is not bytes
        or not raw
        or maximum < 1
        or len(raw) > maximum
        or b"\r" in raw
        or not raw.isascii()
    ):
        raise _launchd_refusal(code)
    text = raw.decode("ascii")
    if text.endswith("\n"):
        text = text[:-1]
    if "\n" in text or not _launchd_is_safe_text(text) or text != text.strip(" "):
        raise _launchd_refusal(code)
    return text


def _require_qualified_kernel_profile() -> None:
    """Accept only the observed Darwin 25.5 kernel family. No guessed futures."""
    release = _bounded_single_line(
        _run_bounded(_SYSCTL_OSRELEASE_ARGV, max_bytes=_LAUNCHD_MAX_KERNEL_BYTES),
        maximum=_LAUNCHD_MAX_KERNEL_BYTES,
        code="SERVICE_LAUNCHCTL_PROFILE_UNQUALIFIED",
    )
    if not _LAUNCHD_KERNEL_PATTERN.fullmatch(release):
        raise _launchd_refusal("SERVICE_LAUNCHCTL_PROFILE_UNQUALIFIED")


def _observe_launchd_service(role: str) -> _LaunchdObservation:
    """Read one closed system service through launchd's own account of itself.

    Live observations are never cached: every call re-runs both fixed commands.
    Argument, working-directory, and on-disk pin checks belong to the forthcoming
    file-closure factory and are deliberately not claimed here.
    """
    spec = _launchd_role_spec(role)
    _require_qualified_kernel_profile()
    raw = _run_bounded(spec.launchctl_argv, max_bytes=_LAUNCHD_MAX_BYTES)
    return _parse_launchctl_service(raw, role=role)


def _observe_real_boot_id() -> str:
    """Return the kernel boot-session UUID, lowercased. Never a derived guess."""
    value = _bounded_single_line(
        _run_bounded(_SYSCTL_BOOT_ID_ARGV, max_bytes=_LAUNCHD_MAX_BOOT_ID_BYTES),
        maximum=_LAUNCHD_MAX_BOOT_ID_BYTES,
        code="SERVICE_BOOT_UUID_MALFORMED",
    ).lower()
    if not _LAUNCHD_UUID_PATTERN.fullmatch(value):
        raise _launchd_refusal("SERVICE_BOOT_UUID_MALFORMED")
    if not any(char != "0" for char in value.replace("-", "")):
        raise _launchd_refusal("SERVICE_BOOT_UUID_NIL")
    return value
