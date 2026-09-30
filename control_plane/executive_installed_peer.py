"""Private installed-service peer qualification for Darwin.

Joins a genuine A2 connection capture with live launchd/dynamic-code identity,
root-owned exact release and runtime closures, and immutable configuration.
The consumer remains separately disarmed until installed qualification. This
module cannot install a release, approve an effect, or alter Runtime state."""

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


class _ProcUniqueIdentifierInfo(ctypes.Structure):
    """Darwin PROC_PIDUNIQIDENTIFIERINFO ABI, fixed at 56 bytes.

    Apple XNU f6217f891ac0bb64f3d375211650a4c1ff8ca1ea,
    bsd/sys/proc_info_private.h. Parent and executable fields are deliberately
    excluded from the returned process-instance observation.
    """

    _fields_ = [
        ("p_uuid", ctypes.c_ubyte * 16),
        ("p_uniqueid", ctypes.c_uint64),
        ("p_puniqueid", ctypes.c_uint64),
        ("p_idversion", ctypes.c_int32),
        ("p_orig_ppidversion", ctypes.c_int32),
        ("p_reserve2", ctypes.c_uint64),
        ("p_reserve3", ctypes.c_uint64),
    ]


@dataclass(frozen=True, slots=True)
class _ProcessInstanceObservation:
    """Kernel process/exec identity only; neither peer nor effect authority."""

    unique_id: int
    pidversion: int


def _observe_process_instance(pid: int) -> _ProcessInstanceObservation:
    """Read one internally supplied PID; production role wiring is separate.

    This private primitive does not qualify a service or replace the existing
    socket audit-token observer. Each call reads a fresh kernel result.
    """
    if type(pid) is not int or not 0 < pid <= (1 << 31) - 1:
        raise PeerIdentityError("SERVICE_PROCESS_PID_INVALID")
    if sys.platform != "darwin":
        raise PeerIdentityError("PEER_PLATFORM_UNSUPPORTED")
    try:
        if ctypes.sizeof(_ProcUniqueIdentifierInfo) != 56 or ctypes.sizeof(ctypes.c_int) != 4:
            raise PeerIdentityError("SERVICE_PROCESS_ABI_UNSUPPORTED")
        library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        query = library.proc_pidinfo
        query.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
            ctypes.c_void_p, ctypes.c_int,
        ]
        query.restype = ctypes.c_int
        observed = _ProcUniqueIdentifierInfo()
        ctypes.set_errno(0)
        size = query(pid, 17, 0, ctypes.byref(observed), 56)
    except PeerIdentityError:
        raise
    except Exception:
        raise PeerIdentityError("SERVICE_PROCESS_OBSERVATION_UNAVAILABLE") from None
    if type(size) is not int or size != 56:
        raise PeerIdentityError("SERVICE_PROCESS_OBSERVATION_SIZE_INVALID")
    if observed.p_uniqueid <= 0 or observed.p_idversion <= 0:
        raise PeerIdentityError("SERVICE_PROCESS_IDENTITY_INVALID")
    return _ProcessInstanceObservation(observed.p_uniqueid, observed.p_idversion)


@dataclass(frozen=True, slots=True)
class _DynamicCodeObservation:
    """Immutable dynamic-code snapshot. Not authority and not a public record."""

    designated_requirement_digest: str
    dynamic_code_identity_digest: str
    dynamic_code_status: int
    executable_path: str


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
    closed = False
    try:
        if process.poll() is None:
            process.kill()
    except Exception:
        pass
    stream = getattr(process, "stdout", None)
    if stream is not None:
        try:
            stream.close()
            closed = True
        except Exception:
            pass
    try:
        process.wait(timeout=_LAUNCHD_REAP_GRACE_SECONDS)
    except Exception:
        return False
    return closed


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



# ---------------------------------------------------------------------------
# Appended private installed-service factory slice.
#
# Everything above this marker is the frozen R5 dynamic-code primitive and the
# frozen R6 bounded launchd/boot observer; neither is rewritten here. The code
# below assembles those reviewed primitives into the complete private
# installed-service factory for the two closed roles, and is the ONLY place in
# this module that composes an owner observation. No public consumer is wired:
# the single exported name is still qualify_installed_peer.
# ---------------------------------------------------------------------------

import json                                             # noqa: E402
import math                                             # noqa: E402
import plistlib                                         # noqa: E402
import stat                                             # noqa: E402
from xml.etree import ElementTree                       # noqa: E402

from control_plane import executive_peer_identity as _peer_identity  # noqa: E402
from control_plane.fs_security import (                 # noqa: E402
    FilesystemSecurityError,
    has_macos_acl,
)

_MAX_READ_BYTES = 32 * 1024 * 1024
_MAX_CLOSURE_BYTES = 256 * 1024 * 1024
_MAX_DIRECTORY_ENTRIES = 4096
_MAX_WALK_ENTRIES = 8192
_MAX_NAME_BYTES = 255
_SERVICE_BUDGET_SECONDS = 25.0

_SERVICE_ROOT = "/Library/Application Support/MastermindExecutive"
_SERVICE_RELEASES = _SERVICE_ROOT + "/releases"
_SERVICE_NETWORK_RUNTIMES = _SERVICE_ROOT + "/network-runtimes"
_CONTROL_CONFIG_PATH = _SERVICE_ROOT + "/config/control.json"
_GATEWAY_CONFIG_PATH = _SERVICE_ROOT + "/config/executive-mcp.json"

_PYTHON_BASE = "/Library/Frameworks/Python.framework/Versions/3.12"
_PYTHON_FRAMEWORK = _PYTHON_BASE
_PYTHON_LAUNCHER = _PYTHON_BASE + "/bin/python3.12"
_PYTHON_DYLIB = _PYTHON_BASE + "/Python"
_PYTHON_MAIN_EXECUTABLE = (
    _PYTHON_BASE + "/Resources/Python.app/Contents/MacOS/Python"
)
_PYTHON_PATCHLEVEL = _PYTHON_BASE + "/include/python3.12/patchlevel.h"
_PYTHON_VERSION = "3.12.10"
_PYTHON_LAUNCHER_SHA256 = (
    "d4f152f2a753c94e0e7935c8ebbe6b2609979e1df7898422b577d0076383d08b"
)
_PYTHON_DYLIB_SHA256 = (
    "14e61fb22a897d238248dfd8fe3b472b4541338c293368b4747803055b8bb3aa"
)
_PYTHON_MAIN_SHA256 = (
    "93d04da16de15e537a76fa1278accf982dd35ff1107e06460433315512eb381f"
)
_PYTHON_TEAM_IDENTIFIER = "BMM5U3QVKW"
_PYTHON_PACKAGE_SHA256 = (
    "8373e58da4ea146b3eb1c1f9834f19a319440b6b679b06050b1f9ee3237aa8e4"
)

# Fixed, separately qualified internal symlinks of the PSF base. Any other
# symlink, or any drift in these, refuses.
_PYTHON_BASE_LINKS = (
    ("Headers", "include/python3.12"),
    ("bin/2to3", "2to3-3.12"),
    ("bin/idle3", "idle3.12"),
    ("bin/pydoc3", "pydoc3.12"),
    ("bin/python3", "python3.12"),
    ("bin/python3-config", "python3.12-config"),
    ("bin/python3-intel64", "python3.12-intel64"),
    ("lib/libcrypto.dylib", "libcrypto.3.dylib"),
    ("lib/libcurses.dylib", "libncurses.6.dylib"),
    ("lib/libform.dylib", "libform.6.dylib"),
    ("lib/libmenu.dylib", "libmenu.6.dylib"),
    ("lib/libncurses.dylib", "libncurses.6.dylib"),
    ("lib/libpanel.dylib", "libpanel.6.dylib"),
    ("lib/libpython3.12.dylib", "../Python"),
    ("lib/libssl.dylib", "libssl.3.dylib"),
    ("lib/pkgconfig/python3-embed.pc", "python-3.12-embed.pc"),
    ("lib/pkgconfig/python3.pc", "python-3.12.pc"),
    ("lib/python3.12/config-3.12-darwin/libpython3.12.a", "../../../Python"),
    ("lib/python3.12/config-3.12-darwin/libpython3.12.dylib", "../../../Python"),
    ("share/man/man1/python3.1", "python3.12.1"),
)


# Qualified gateway network-runtime closure. Embedded pinned content: never
# learned from the tree under test and never re-baselined.
_NETWORK_RUNTIME_NAME = (
    "9512f58e382dbb94c730f74a0d80935e460f6c2707da7689b4beaecead9cb94d"
)
_NETWORK_RUNTIME_ROOT = _SERVICE_NETWORK_RUNTIMES + "/" + _NETWORK_RUNTIME_NAME
_NETWORK_RUNTIME_LAUNCHER = _NETWORK_RUNTIME_ROOT + "/bin/python"
_NETWORK_CLOSURE_SCHEMA = "mastermind.executive_network_closure/v1"
_NETWORK_CLOSURE_DOMAIN = b"MMX_EXECUTIVE_NETWORK_RUNTIME_CLOSURE_V1"
_NETWORK_CLOSURE_PIN_SHA256 = (
    "e799725fd46fd7746d5ad6f1e17243517945ed26c2d421a8710ae31871bc0cdb"
)
_NETWORK_CLOSURE_FILE_COUNT = 2533
_NETWORK_CLOSURE_DIRECTORY_COUNT = 378
_NETWORK_CLOSURE_TOTAL_BYTES = 46298728
_NETWORK_MANIFEST_NAME = ".executive-release-manifest.json"
_RELEASE_MANIFEST_SCHEMA = "mastermind.executive_release_manifest/v1"
_GATEWAY_CONFIG_SCHEMA = "mastermind.executive_mcp_install.v1"
_GATEWAY_MCP_PROFILE = "release_control_v1"
_GATEWAY_MCP_PROFILES = (_GATEWAY_MCP_PROFILE, "web_ceo_release_v1")
_RELEASE_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}")
_RELEASE_PLACEHOLDER = "{release}"

_CODESIGN_VERIFY_ARGV = (
    "/usr/bin/codesign",
    "--verify",
    "--deep",
    "--strict",
    _PYTHON_FRAMEWORK,
)
_CODESIGN_METADATA_ARGV = (
    "/usr/bin/codesign",
    "--display",
    "--verbose=4",
    "--entitlements",
    ":-",
    _PYTHON_MAIN_EXECUTABLE,
)



@dataclass(frozen=True, slots=True)
class _RoleTopology:
    """Closed nonsecret filesystem/identity topology for exactly one role."""

    role: str
    service_uid: int
    username: str
    group: str
    config_path: str
    config_gid: int
    config_mode: int
    config_release_field: str
    wrapper_relative: str
    launcher: str
    network_closure: bool


_ROLE_TOPOLOGIES = {
    "control": _RoleTopology(
        role="control",
        service_uid=450,
        username="_mastermind_exec",
        group="_mastermind_exec",
        config_path=_CONTROL_CONFIG_PATH,
        config_gid=450,
        config_mode=0o440,
        config_release_field="proof_base_sha",
        wrapper_relative="scripts/executive_os_phase1c_control_wrapper.py",
        launcher=_PYTHON_LAUNCHER,
        network_closure=False,
    ),
    "gateway": _RoleTopology(
        role="gateway",
        service_uid=458,
        username="_mastermind_executive_mcp",
        group="_mastermind_executive_mcp",
        config_path=_GATEWAY_CONFIG_PATH,
        config_gid=0,
        config_mode=0o644,
        config_release_field="release_sha",
        wrapper_relative="ops/executive_os/executive_mcp_entry.py",
        launcher=_NETWORK_RUNTIME_LAUNCHER,
        network_closure=True,
    ),
}

_CONTROL_SOCKETS = {
    "CeoIngress": {
        "SockPassive": True,
        "SockPathGroup": 452,
        "SockPathMode": 432,
        "SockPathName": "/var/run/mastermind-executive/ceo-ingress.sock",
        "SockPathOwner": 450,
        "SockType": "stream",
    },
    "DialogueObservation": {
        "SockPassive": True,
        "SockPathGroup": 457,
        "SockPathMode": 432,
        "SockPathName": (
            "/var/run/mastermind-dialogue-observation/"
            "dialogue-observation.sock"
        ),
        "SockPathOwner": 450,
        "SockType": "stream",
    },
    "Operator": {
        "SockPassive": True,
        "SockPathGroup": 453,
        "SockPathMode": 432,
        "SockPathName": "/var/run/mastermind-executive/control.sock",
        "SockPathOwner": 450,
        "SockType": "stream",
    },
}

# Closed expected plist profiles. The only permitted variation is the exact
# release-SHA path substitution performed by _profile_matches below; nothing is
# read from any fixture file at production runtime.
_EXPECTED_PLIST_PROFILES = {
    "control": {
        "AbandonProcessGroup": False,
        "EnvironmentVariables": {
            "HOME": "/var/db/mastermind-executive/control/home",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "NO_COLOR": "1",
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "PYTHONUNBUFFERED": "1",
            "TZ": "UTC",
        },
        "ExitTimeOut": 15,
        "GroupName": "_mastermind_exec",
        "HardResourceLimits": {"Core": 0, "FileSize": 67108864},
        "KeepAlive": True,
        "Label": "com.mastermind.executive.control",
        "ProcessType": "Interactive",
        "ProgramArguments": [
            _PYTHON_LAUNCHER,
            "-I",
            "-S",
            "-B",
            _RELEASE_PLACEHOLDER + "/scripts/executive_os_phase1c_control_wrapper.py",
            "--config",
            _CONTROL_CONFIG_PATH,
            "--sentinel-file",
            _SERVICE_ROOT + "/config/control-env-canary",
            "--attestation",
            "/var/db/mastermind-executive/control/canaries/"
            "control-environment-attestation.json",
            "--release-root",
            _RELEASE_PLACEHOLDER,
        ],
        "RunAtLoad": True,
        "Sockets": _CONTROL_SOCKETS,
        "StandardErrorPath": "/var/log/mastermind-executive/control/stderr.log",
        "StandardOutPath": "/var/log/mastermind-executive/control/stdout.log",
        "ThrottleInterval": 10,
        "Umask": 63,
        "UserName": "_mastermind_exec",
        "WorkingDirectory": _RELEASE_PLACEHOLDER,
    },
    "gateway": {
        "EnvironmentVariables": {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        },
        "GroupName": "_mastermind_executive_mcp",
        "KeepAlive": True,
        "Label": "com.mastermind.executive.mcp",
        "ProcessType": "Background",
        "ProgramArguments": [
            _NETWORK_RUNTIME_LAUNCHER,
            "-I",
            "-B",
            _RELEASE_PLACEHOLDER + "/ops/executive_os/executive_mcp_entry.py",
            "--config",
            _GATEWAY_CONFIG_PATH,
        ],
        "RunAtLoad": True,
        "StandardErrorPath": (
            "/var/log/mastermind-executive/mcp-auth/service.stderr.log"
        ),
        "StandardOutPath": (
            "/var/log/mastermind-executive/mcp-auth/service.stdout.log"
        ),
        "ThrottleInterval": 10,
        "Umask": 63,
        "UserName": "_mastermind_executive_mcp",
        "WorkingDirectory": _RELEASE_PLACEHOLDER,
    },
}


def _lstat(path: str) -> os.stat_result:
    """Single lstat seam so link races stay testable without root."""
    return os.lstat(path)


def _readlink(path: str) -> str:
    """Single readlink seam for the closed qualified symlink profiles."""
    return os.readlink(path)


def _refuse(code: str) -> PeerIdentityError:
    """Build the only outward failure shape: a short nonsecret code."""
    return PeerIdentityError(code)


def _role_topology(role: object) -> _RoleTopology:
    if type(role) is not str:
        raise _refuse("SERVICE_ROLE_UNSUPPORTED")
    topology = _ROLE_TOPOLOGIES.get(role) if type(role) is str else None
    if topology is None:
        raise _refuse("SERVICE_ROLE_UNSUPPORTED")
    return topology


class _Budget:
    """One monotonic qualification budget; every read/walk/child obeys it."""

    __slots__ = ("_deadline",)

    def __init__(self, seconds: float):
        self._deadline = time.monotonic() + seconds

    def remaining(self) -> float:
        return self._deadline - time.monotonic()

    def check(self, code: str = "SERVICE_QUALIFICATION_BUDGET_EXCEEDED") -> float:
        remaining = self.remaining()
        if remaining <= 0:
            raise _refuse(code)
        return remaining


def _object_identity(info: os.stat_result) -> tuple:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_uid,
        info.st_gid,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _require_clean_text(value: object, *, code: str) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= _MAX_NAME_BYTES * 16
        or not value.isascii()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _refuse(code)
    return value


def _require_no_acl(
    path: str,
    before: os.stat_result,
    *,
    descriptor: int | None = None,
    code: str,
    allow_symlink: bool = False,
) -> bool:
    """Return whether ACL entries exist; every API error refuses."""
    try:
        if allow_symlink:
            return has_macos_acl(
                path, expected_identity=before, allow_symlink=True
            )
        if descriptor is None:
            return has_macos_acl(path, expected_identity=before)
        return has_macos_acl(
            path, expected_identity=before, descriptor=descriptor
        )
    except (FilesystemSecurityError, OSError, ValueError):
        raise _refuse(code) from None


def _open_trusted(
    path: str,
    *,
    budget: _Budget,
    ancestor: bool = False,
    allow_symlink: str | None = None,
    expected_gid: int = 0,
) -> tuple:
    """lstat/open/fstat one object with no-follow trust and no ACL.

    Returns (descriptor, fstat). Ancestors may keep their qualified real group;
    trusted objects themselves must be root:wheel with no group/other write.
    """
    budget.check()
    try:
        before = _lstat(path)
    except OSError:
        raise _refuse("SERVICE_OBJECT_UNAVAILABLE") from None
    if before.st_uid != 0:
        raise _refuse("SERVICE_OBJECT_NOT_ROOT_OWNED")
    if not ancestor:
        if before.st_gid != expected_gid:
            raise _refuse("SERVICE_OBJECT_NOT_ROOT_GROUP")
        if stat.S_IMODE(before.st_mode) & 0o022:
            raise _refuse("SERVICE_OBJECT_GROUP_WRITABLE")
    elif stat.S_IMODE(before.st_mode) & 0o022:
        raise _refuse("SERVICE_ANCESTOR_GROUP_WRITABLE")
    if allow_symlink is None:
        if stat.S_ISLNK(before.st_mode):
            raise _refuse("SERVICE_UNQUALIFIED_SYMLINK")
        if not (stat.S_ISDIR(before.st_mode) or stat.S_ISREG(before.st_mode)):
            raise _refuse("SERVICE_OBJECT_TYPE_UNSUPPORTED")
        flags = (
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
    else:
        if not stat.S_ISLNK(before.st_mode):
            raise _refuse("SERVICE_UNQUALIFIED_SYMLINK")
        flags = os.O_RDONLY | getattr(os, "O_SYMLINK", 0) | getattr(
            os, "O_CLOEXEC", 0
        )
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise _refuse("SERVICE_OBJECT_UNAVAILABLE") from None
    try:
        try:
            observed = os.fstat(descriptor)
        except OSError:
            raise _refuse("SERVICE_OBJECT_UNAVAILABLE") from None
        if _object_identity(observed) != _object_identity(before):
            raise _refuse("SERVICE_OBJECT_IDENTITY_CHANGED")
        observed_acl = _require_no_acl(
            path,
            before,
            code="SERVICE_ACL_OBSERVATION_FAILED",
            descriptor=None if allow_symlink is not None else descriptor,
            allow_symlink=allow_symlink is not None,
        )
        if observed_acl:
            raise _refuse(
                "SERVICE_ANCESTOR_ACL_PRESENT"
                if ancestor
                else "SERVICE_ACL_PRESENT"
            )
        if _object_identity(os.fstat(descriptor)) != _object_identity(before) or _object_identity(_lstat(path)) != _object_identity(before):
            raise _refuse("SERVICE_OBJECT_IDENTITY_CHANGED")
        budget.check()
        return descriptor, observed, before
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            raise _refuse("SERVICE_DESCRIPTOR_CLEANUP_UNPROVEN") from None
        raise


def _close(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:
        raise _refuse("SERVICE_DESCRIPTOR_CLEANUP_UNPROVEN") from None


def _read_trusted_bytes(
    path: str,
    *,
    budget: _Budget,
    maximum: int,
    expected_mode: int | None = None,
    expected_gid: int | None = None,
) -> tuple:
    """Read one regular, hardlink-count-1, root-owned object; return bytes."""
    descriptor, observed, before = _open_trusted(path, budget=budget, expected_gid=0 if expected_gid is None else expected_gid)
    try:
        if not stat.S_ISREG(observed.st_mode):
            raise _refuse("SERVICE_OBJECT_TYPE_UNSUPPORTED")
        if observed.st_nlink != 1:
            raise _refuse("SERVICE_OBJECT_MULTILINK")
        if expected_mode is not None and stat.S_IMODE(observed.st_mode) != expected_mode:
            raise _refuse("SERVICE_OBJECT_MODE_MISMATCH")
        if expected_gid is not None and observed.st_gid != expected_gid:
            raise _refuse("SERVICE_OBJECT_NOT_ROOT_GROUP")
        if observed.st_size > maximum:
            raise _refuse("SERVICE_OBJECT_TOO_LARGE")
        chunks = []
        consumed = 0
        while True:
            budget.check()
            block = os.read(descriptor, min(65536, maximum + 1 - consumed))
            if not block:
                break
            consumed += len(block)
            if consumed > maximum:
                raise _refuse("SERVICE_OBJECT_TOO_LARGE")
            chunks.append(block)
        data = b"".join(chunks)
        if len(data) != observed.st_size:
            raise _refuse("SERVICE_OBJECT_CHANGED_DURING_READ")
        try:
            after = os.fstat(descriptor)
        except OSError:
            raise _refuse("SERVICE_OBJECT_UNAVAILABLE") from None
        if _object_identity(after) != _object_identity(observed):
            raise _refuse("SERVICE_OBJECT_CHANGED_DURING_READ")
        if _object_identity(_lstat(path)) != _object_identity(observed):
            raise _refuse("SERVICE_OBJECT_CHANGED_DURING_READ")
        budget.check()
        return data, observed
    finally:
        _close(descriptor)
        budget.check()


def _strict_json_object(pairs: list) -> dict:
    seen = set()
    for key, _value in pairs:
        if key in seen:
            raise _refuse("SERVICE_DOCUMENT_DUPLICATE_KEY")
        seen.add(key)
    return dict(pairs)


def _reject_constant(_value: str):
    raise _refuse("SERVICE_DOCUMENT_NONFINITE_NUMBER")


def _finite_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise _refuse("SERVICE_DOCUMENT_NONFINITE_NUMBER")
    return parsed


def _load_strict_json(raw: bytes, *, code: str) -> dict:
    if type(raw) is not bytes or not raw or len(raw) > _MAX_READ_BYTES:
        raise _refuse(code)
    if not raw.isascii() or b"\x00" in raw:
        raise _refuse(code)
    try:
        document = json.loads(
            raw.decode("ascii"),
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_constant,
            parse_float=_finite_json_float,
        )
    except PeerIdentityError:
        raise
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise _refuse(code) from None
    if type(document) is not dict:
        raise _refuse(code)
    return document


def _load_strict_plist(raw: bytes, *, code: str) -> dict:
    """Parse one bounded XML plist, refusing ambiguous duplicate dict keys."""
    if type(raw) is not bytes or not raw or len(raw) > 262144:
        raise _refuse(code)
    if not raw.lstrip()[:5].startswith(b"<?xml") or b"<!ENTITY" in raw.upper():
        raise _refuse(code)
    budget_elements = [0]
    try:
        root = ElementTree.fromstring(raw)
    except (ElementTree.ParseError, ValueError, RecursionError):
        raise _refuse(code) from None
    if root.tag != "plist":
        raise _refuse(code)

    def walk(node, depth: int) -> None:
        budget_elements[0] += 1
        if depth > 12 or budget_elements[0] > 4096:
            raise _refuse(code)
        if node.tag == "dict":
            children = list(node)
            if len(children) % 2 != 0:
                raise _refuse(code)
            keys = set()
            for index, child in enumerate(children):
                if index % 2 == 0:
                    if child.tag != "key" or type(child.text) is not str:
                        raise _refuse(code)
                    if child.text in keys:
                        raise _refuse(code)
                    keys.add(child.text)
                    continue
                if child.tag == "key":
                    raise _refuse(code)
                walk(child, depth + 1)
            return
        if node.tag in ("array",):
            for child in node:
                walk(child, depth + 1)
            return
        if node.tag in ("string", "integer", "real", "true", "false", "data",
                        "date"):
            return
        raise _refuse(code)

    top = list(root)
    if len(top) != 1 or top[0].tag != "dict":
        raise _refuse(code)
    walk(top[0], 0)
    try:
        value = plistlib.loads(raw)
    except Exception:
        raise _refuse(code) from None
    if type(value) is not dict:
        raise _refuse(code)
    return value


_READ_ONLY_COMMANDS = (_CODESIGN_VERIFY_ARGV, _CODESIGN_METADATA_ARGV)


def _profile_matches(template: object, value: object, releases: list) -> bool:
    """Closed structural match; only exact release-SHA substitution may vary."""
    if type(template) is str:
        if type(value) is not str or not value.isascii():
            return False
        if _RELEASE_PLACEHOLDER not in template:
            return value == template
        substitution = "(" + re.escape(_SERVICE_RELEASES) + r"/[0-9a-f]{40})"
        pattern = re.escape(template).replace(
            re.escape(_RELEASE_PLACEHOLDER), substitution
        )
        matched = re.fullmatch(pattern, value)
        if matched is None:
            return False
        prefix = _SERVICE_RELEASES + "/"
        for item in matched.groups():
            discovered = item[len(prefix):]
            if (
                _RELEASE_SHA_PATTERN.fullmatch(discovered) is None
                or (releases and discovered != releases[0])
            ):
                return False
            if discovered not in releases:
                releases.append(discovered)
        return True
    if type(template) is bool:
        return type(value) is bool and value == template
    if type(template) is int:
        return type(value) is int and value == template
    if type(template) is dict:
        return (
            type(value) is dict
            and set(value) == set(template)
            and all(
                _profile_matches(template[key], value[key], releases)
                for key in template
            )
        )
    if type(template) is list:
        return (
            type(value) is list
            and len(value) == len(template)
            and all(
                _profile_matches(expected, actual, releases)
                for expected, actual in zip(template, value)
            )
        )
    return False


def _release_directory(release: str) -> str:
    if type(release) is not str or _RELEASE_SHA_PATTERN.fullmatch(release) is None:
        raise _refuse("SERVICE_RELEASE_IDENTITY_MALFORMED")
    return _SERVICE_RELEASES + "/" + release


def _observe_ancestors(path: str, budget: _Budget) -> tuple:
    """Root-own/no-ACL/no-group-write identity for every direct ancestor."""
    observed = []
    current = path
    depth = 0
    while True:
        parent = current.rsplit("/", 1)[0] or "/"
        if parent == current:
            break
        depth += 1
        if depth > 16:
            raise _refuse("SERVICE_ANCESTOR_DEPTH_EXCEEDED")
        descriptor, identity, _before = _open_trusted(
            parent, budget=budget, ancestor=True
        )
        _close(descriptor)
        observed.append((parent, _object_identity(identity)))
        current = parent
    return tuple(reversed(observed))


@dataclass(frozen=True, slots=True)
class _PlistObservation:
    release: str
    digest: str
    argv: tuple
    identity: tuple
    ancestor_identities: tuple


def _verify_role_plist(
    topology: _RoleTopology, budget: _Budget, *, expected_release: str | None = None
) -> _PlistObservation:
    """Read and structurally match one closed launchd plist profile."""
    role = topology.role
    path = _LAUNCHD_ROLES[role].plist_path
    ancestors = _observe_ancestors(path, budget)
    raw, identity = _read_trusted_bytes(
        path, budget=budget, maximum=262144, expected_mode=0o644
    )
    document = _load_strict_plist(raw, code="SERVICE_PLIST_MALFORMED")
    releases: list = []
    if not _profile_matches(_EXPECTED_PLIST_PROFILES[role], document, releases):
        raise _refuse("SERVICE_PLIST_PROFILE_DRIFT")
    if len(releases) != 1:
        raise _refuse("SERVICE_PLIST_RELEASE_AMBIGUOUS")
    release = releases[0]
    if expected_release is not None and release != expected_release:
        raise _refuse("SERVICE_PLIST_RELEASE_MISMATCH")
    argv = document["ProgramArguments"]
    if type(argv) is not list or not argv or type(argv[0]) is not str:
        raise _refuse("SERVICE_PLIST_PROFILE_DRIFT")
    return _PlistObservation(
        release=release,
        digest=hashlib.sha256(raw).hexdigest(),
        argv=tuple(argv),
        identity=_object_identity(identity),
        ancestor_identities=_joined(_observe_ancestors(path, budget), ancestors, "SERVICE_ANCESTOR_CHANGED"),
    )


@dataclass(frozen=True, slots=True)
class _ConfigObservation:
    digest: str
    provenance_digest: str
    release: str
    identity: tuple
    ancestor_identities: tuple


def _require_document_text(document: dict, name: str, *, code: str) -> str:
    value = document.get(name)
    if (
        type(value) is not str
        or not 1 <= len(value) <= 4096
        or not value.isascii()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _refuse(code)
    return value


def _require_document_int(document: dict, name: str, *, code: str) -> int:
    value = document.get(name)
    if type(value) is not int or type(value) is bool:
        raise _refuse(code)
    return value


def _require_digest(document: dict, name: str, *, code: str) -> str:
    value = _require_document_text(document, name, code=code)
    if _DIGEST_PATTERN.fullmatch(value) is None or set(value) == {"0"}:
        raise _refuse(code)
    return value


def _require_release(document: dict, name: str, *, code: str) -> str:
    value = _require_document_text(document, name, code=code)
    if _RELEASE_SHA_PATTERN.fullmatch(value) is None or not any(c != "0" for c in value):
        raise _refuse(code)
    return value


def _verify_control_projection(budget: _Budget) -> _ConfigObservation:
    """Read the fixed trusted Control config that carries the Python projection.

    The same snapshot is consumed for either role: this is provenance evidence
    projected by the existing root installer, never a caller-supplied value and
    never release approval or arming.
    """
    ancestors = _observe_ancestors(_CONTROL_CONFIG_PATH, budget)
    raw, identity = _read_trusted_bytes(
        _CONTROL_CONFIG_PATH,
        budget=budget,
        maximum=4194304,
        expected_mode=0o440,
        expected_gid=450,
    )
    document = _load_strict_json(raw, code="SERVICE_CONFIG_MALFORMED")
    release = _require_release(document, "proof_base_sha", code="SERVICE_CONFIG_SCHEMA_DRIFT")
    if _require_document_int(document, "control_uid", code="SERVICE_CONFIG_SCHEMA_DRIFT") != 450:
        raise _refuse("SERVICE_CONFIG_SCHEMA_DRIFT")
    projection = _require_digest(
        document,
        "python_runtime_provenance_digest",
        code="SERVICE_PYTHON_PROVENANCE_MISSING",
    )
    return _ConfigObservation(
        digest=hashlib.sha256(raw).hexdigest(),
        provenance_digest=projection,
        release=release,
        identity=_object_identity(identity),
        ancestor_identities=_joined(_observe_ancestors(_CONTROL_CONFIG_PATH, budget), ancestors, "SERVICE_ANCESTOR_CHANGED"),
    )


def _verify_role_config(
    topology: _RoleTopology, release: str, budget: _Budget
) -> _ConfigObservation:
    ancestors = _observe_ancestors(topology.config_path, budget)
    raw, identity = _read_trusted_bytes(
        topology.config_path,
        budget=budget,
        maximum=4194304,
        expected_mode=topology.config_mode,
        expected_gid=topology.config_gid,
    )
    document = _load_strict_json(raw, code="SERVICE_CONFIG_MALFORMED")
    if topology.role == "control":
        if _require_release(document, "proof_base_sha", code="SERVICE_CONFIG_SCHEMA_DRIFT") != release:
            raise _refuse("SERVICE_CONFIG_RELEASE_MISMATCH")
        if _require_document_int(document, "control_uid", code="SERVICE_CONFIG_SCHEMA_DRIFT") != 450:
            raise _refuse("SERVICE_CONFIG_UID_DRIFT")
    else:
        if _require_document_text(document, "schema", code="SERVICE_CONFIG_SCHEMA_DRIFT") != _GATEWAY_CONFIG_SCHEMA:
            raise _refuse("SERVICE_CONFIG_SCHEMA_DRIFT")
        if _require_document_int(document, "service_uid", code="SERVICE_CONFIG_SCHEMA_DRIFT") != 458:
            raise _refuse("SERVICE_CONFIG_UID_DRIFT")
        if _require_document_text(document, "executive_mcp_profile", code="SERVICE_CONFIG_SCHEMA_DRIFT") not in _GATEWAY_MCP_PROFILES:
            raise _refuse("SERVICE_CONFIG_PROFILE_DRIFT")
        if _require_release(document, "release_sha", code="SERVICE_CONFIG_SCHEMA_DRIFT") != release:
            raise _refuse("SERVICE_CONFIG_RELEASE_MISMATCH")
    return _ConfigObservation(
        digest=hashlib.sha256(raw).hexdigest(),
        provenance_digest="",
        release=release,
        identity=_object_identity(identity),
        ancestor_identities=_joined(_observe_ancestors(topology.config_path, budget), ancestors, "SERVICE_ANCESTOR_CHANGED"),
    )


# Qualified release symlink support is deliberately closed to the one existing
# safe relative link; anything else refuses until separately qualified.
_RELEASE_SYMLINKS = {"vendor/macro": "macro_src"}


@dataclass(frozen=True, slots=True)
class _TreeObservation:
    release: str
    wrapper_relative: str
    manifest_digest: str
    wrapper_digest: str
    identities: tuple
    digests: tuple
    root_identity: tuple
    ancestor_identities: tuple
    manifest_identity: tuple


def _directory_entries(directory: str, budget: _Budget) -> list:
    budget.check()
    try:
        with os.scandir(directory) as scan:
            names = []
            for entry in scan:
                budget.check()
                if not entry.name or entry.name in (".", "..") or "/" in entry.name or not entry.name.isascii():
                    raise _refuse("SERVICE_DIRECTORY_NAME_MALFORMED")
                names.append(entry.name)
                if len(names) > _MAX_DIRECTORY_ENTRIES:
                    raise _refuse("SERVICE_DIRECTORY_ENTRY_LIMIT")
    except PeerIdentityError:
        raise
    except OSError:
        raise _refuse("SERVICE_DIRECTORY_UNREADABLE") from None
    budget.check()
    return sorted(names)


def _walk_release(
    release_path: str, budget: _Budget, *, hash_files: bool = True
) -> list:
    """Inventory every real release entry without following any link."""
    rows = []
    pending = [("", release_path)]
    while pending:
        relative, directory = pending.pop()
        for name in _directory_entries(directory, budget):
            if len(name) > _MAX_NAME_BYTES or not name.isascii():
                raise _refuse("SERVICE_RELEASE_NAME_MALFORMED")
            child_relative = name if not relative else relative + "/" + name
            if child_relative == _NETWORK_MANIFEST_NAME:
                continue
            if len(rows) >= _MAX_WALK_ENTRIES:
                raise _refuse("SERVICE_RELEASE_ENTRY_LIMIT")
            child = directory + "/" + name
            try:
                info = _lstat(child)
            except OSError:
                raise _refuse("SERVICE_OBJECT_UNAVAILABLE") from None
            if info.st_uid != 0 or info.st_gid != 0:
                raise _refuse("SERVICE_OBJECT_NOT_ROOT_OWNED")
            if stat.S_IMODE(info.st_mode) & 0o022:
                raise _refuse("SERVICE_OBJECT_GROUP_WRITABLE")
            mode = stat.S_IMODE(info.st_mode)
            if stat.S_ISLNK(info.st_mode):
                qualified = _RELEASE_SYMLINKS.get(child_relative)
                if qualified is None:
                    raise _refuse("SERVICE_UNQUALIFIED_SYMLINK")
                try:
                    target = _readlink(child)
                except OSError:
                    raise _refuse("SERVICE_OBJECT_UNAVAILABLE") from None
                if (
                    target != qualified
                    or target.startswith("/")
                    or any(part in ("", ".", "..") for part in target.split("/"))
                ):
                    raise _refuse("SERVICE_RELEASE_SYMLINK_DRIFT")
                descriptor, observed, before = _open_trusted(
                    child, budget=budget, allow_symlink=child_relative
                )
                _close(descriptor)
                rows.append(
                    (child_relative, "symlink", mode, observed.st_uid,
                     observed.st_gid, 0, "", _object_identity(observed))
                )
                continue
            if stat.S_ISDIR(info.st_mode):
                descriptor, observed, _before = _open_trusted(child, budget=budget)
                _close(descriptor)
                rows.append(
                    (child_relative, "directory", mode, observed.st_uid,
                     observed.st_gid, observed.st_size, "",
                     _object_identity(observed))
                )
                pending.append((child_relative, child))
                continue
            if not stat.S_ISREG(info.st_mode):
                raise _refuse("SERVICE_OBJECT_TYPE_UNSUPPORTED")
            if not hash_files:
                descriptor, observed, _before = _open_trusted(child, budget=budget)
                _close(descriptor)
                if observed.st_nlink != 1:
                    raise _refuse("SERVICE_OBJECT_MULTILINK")
                rows.append(
                    (child_relative, "file", mode, observed.st_uid,
                     observed.st_gid, observed.st_size, "",
                     _object_identity(observed))
                )
                continue
            data, observed = _read_trusted_bytes(
                child, budget=budget, maximum=_MAX_READ_BYTES
            )
            if observed.st_nlink != 1:
                raise _refuse("SERVICE_OBJECT_MULTILINK")
            rows.append(
                (child_relative, "file", mode, observed.st_uid, observed.st_gid,
                 len(data), hashlib.sha256(data).hexdigest(),
                 _object_identity(observed))
            )
    return rows


def _verify_release(
    topology: _RoleTopology, release: str, budget: _Budget
) -> _TreeObservation:
    """Verify the entire real release closure against its root-owned manifest."""
    release_path = _release_directory(release)
    ancestors = _observe_ancestors(release_path, budget)
    descriptor, root_info, _before = _open_trusted(release_path, budget=budget)
    _close(descriptor)
    if not stat.S_ISDIR(root_info.st_mode):
        raise _refuse("SERVICE_RELEASE_NOT_DIRECTORY")
    manifest_path = release_path + "/" + _NETWORK_MANIFEST_NAME
    raw, manifest_info = _read_trusted_bytes(
        manifest_path, budget=budget, maximum=_MAX_READ_BYTES, expected_mode=0o444
    )
    document = _load_strict_json(raw, code="SERVICE_MANIFEST_MALFORMED")
    if set(document) != {"schema_version", "commit_sha", "tree_sha", "entries"}:
        raise _refuse("SERVICE_MANIFEST_KEYS_DRIFT")
    if document["schema_version"] != _RELEASE_MANIFEST_SCHEMA:
        raise _refuse("SERVICE_MANIFEST_SCHEMA_DRIFT")
    if document["commit_sha"] != release:
        raise _refuse("SERVICE_MANIFEST_COMMIT_MISMATCH")
    if (
        type(document["tree_sha"]) is not str
        or _RELEASE_SHA_PATTERN.fullmatch(document["tree_sha"]) is None
    ):
        raise _refuse("SERVICE_MANIFEST_TREE_MALFORMED")
    persisted = document["entries"]
    if type(persisted) is not list or not persisted:
        raise _refuse("SERVICE_MANIFEST_ENTRIES_MALFORMED")
    expected = {}
    for row in persisted:
        if type(row) is not dict:
            raise _refuse("SERVICE_MANIFEST_ENTRIES_MALFORMED")
        kind = row.get("type")
        path = row.get("path")
        if (
            type(path) is not str
            or not path
            or path.startswith("/")
            or any(part in ("", ".") for part in path.split("/"))
            or ".." in path.split("/")
            or type(row.get("mode")) is not int
            or type(row.get("uid")) is not int
            or type(row.get("gid")) is not int
            or path in expected
        ):
            raise _refuse("SERVICE_MANIFEST_ENTRY_MALFORMED")
        if kind == "file":
            if (
                set(row) != {"path", "mode", "uid", "gid", "type", "size", "sha256"}
                or type(row["size"]) is not int
                or _DIGEST_PATTERN.fullmatch(str(row["sha256"])) is None
            ):
                raise _refuse("SERVICE_MANIFEST_ENTRY_MALFORMED")
        elif kind == "directory":
            if set(row) != {"path", "mode", "uid", "gid", "type"}:
                raise _refuse("SERVICE_MANIFEST_ENTRY_MALFORMED")
        elif kind == "symlink":
            if (
                set(row) != {"path", "mode", "uid", "gid", "type", "target"}
                or _RELEASE_SYMLINKS.get(path) != row["target"]
            ):
                raise _refuse("SERVICE_MANIFEST_ENTRY_MALFORMED")
        else:
            raise _refuse("SERVICE_MANIFEST_ENTRY_MALFORMED")
        expected[path] = (kind, row["mode"], row["uid"], row["gid"],
                          row.get("size"), row.get("sha256"), row.get("target"))
    if _NETWORK_MANIFEST_NAME in expected:
        raise _refuse("SERVICE_MANIFEST_SELF_LISTED")
    rows = _walk_release(release_path, budget)
    observed = {row[0]: row for row in rows}
    if len(observed) != len(rows) or set(observed) != set(expected):
        raise _refuse("SERVICE_RELEASE_ENTRY_SET_DRIFT")
    digests = []
    for path, row in sorted(observed.items()):
        kind, mode, uid, gid, size, sha256, target = expected[path]
        if (
            row[1] != kind
            or row[2] != mode
            or row[3] != uid
            or row[4] != gid
        ):
            raise _refuse("SERVICE_RELEASE_METADATA_DRIFT")
        if kind == "file":
            if row[5] != size or row[6] != sha256:
                raise _refuse("SERVICE_RELEASE_HASH_DRIFT")
        elif kind == "directory":
            pass
        elif row[5] != 0:
            raise _refuse("SERVICE_RELEASE_METADATA_DRIFT")
        digests.append((path, kind, mode, uid, gid, size, sha256, row[7]))
    wrapper_relative = topology.wrapper_relative
    wrapper_row = observed.get(wrapper_relative)
    if wrapper_row is None or wrapper_row[1] != "file" or not wrapper_row[6]:
        raise _refuse("SERVICE_WRAPPER_UNQUALIFIED")
    return _TreeObservation(
        release=release,
        wrapper_relative=wrapper_relative,
        manifest_digest=hashlib.sha256(raw).hexdigest(),
        wrapper_digest=wrapper_row[6],
        identities=tuple((row[0], row[7]) for row in sorted(rows)),
        digests=tuple(digests),
        root_identity=_object_identity(root_info),
        ancestor_identities=ancestors,
        manifest_identity=_object_identity(manifest_info),
    )


def _recheck_release(before: _TreeObservation, budget: _Budget) -> None:
    """Re-inventory without trusting the earlier walk: no drift may occur."""
    release_path = _release_directory(before.release)
    descriptor, root_info, _before = _open_trusted(release_path, budget=budget)
    _close(descriptor)
    if _object_identity(root_info) != before.root_identity:
        raise _refuse("SERVICE_RELEASE_CHANGED")
    if _observe_ancestors(release_path, budget) != before.ancestor_identities:
        raise _refuse("SERVICE_ANCESTOR_CHANGED")
    raw, manifest_info = _read_trusted_bytes(
        release_path + "/" + _NETWORK_MANIFEST_NAME,
        budget=budget,
        maximum=_MAX_READ_BYTES,
        expected_mode=0o444,
    )
    if (
        _object_identity(manifest_info) != before.manifest_identity
        or hashlib.sha256(raw).hexdigest() != before.manifest_digest
    ):
        raise _refuse("SERVICE_MANIFEST_CHANGED")
    rows = _walk_release(release_path, budget, hash_files=False)
    if tuple((row[0], row[7]) for row in sorted(rows)) != before.identities:
        raise _refuse("SERVICE_RELEASE_CHANGED")
    wrapper_relative = before.wrapper_relative
    data, _wrapper_info = _read_trusted_bytes(
        release_path + "/" + wrapper_relative, budget=budget, maximum=_MAX_READ_BYTES
    )
    if hashlib.sha256(data).hexdigest() != before.wrapper_digest:
        raise _refuse("SERVICE_WRAPPER_CHANGED")


_PYTHON_LINK_INDEX = {name: target for name, target in _PYTHON_BASE_LINKS}


@dataclass(frozen=True, slots=True)
class _RuntimeObservation:
    launcher_digest: str
    dylib_digest: str
    main_digest: str
    identities: tuple
    link_identities: tuple
    ancestor_identities: tuple


def _run_bounded_readonly(argv: tuple, *, budget: _Budget, max_bytes: int,
                          allow_empty: bool, merge_stderr: bool) -> bytes:
    """Only the two fixed codesign observations; no generic command adapter."""
    if (type(argv) is not tuple or argv not in _READ_ONLY_COMMANDS
        or type(max_bytes) is not int or not 1 <= max_bytes <= _LAUNCHD_MAX_COMMAND_BYTES
        or type(allow_empty) is not bool or allow_empty != (argv == _CODESIGN_VERIFY_ARGV)
        or type(merge_stderr) is not bool or merge_stderr != (argv == _CODESIGN_METADATA_ARGV)):
        raise _refuse("SERVICE_LAUNCHCTL_COMMAND_NOT_ALLOWED")
    if sys.platform != "darwin":
        raise _refuse("PEER_PLATFORM_UNSUPPORTED")
    deadline = time.monotonic() + min(budget.check(), _LAUNCHD_TIMEOUT_SECONDS)
    try:
        process = subprocess.Popen(list(argv), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT if merge_stderr else subprocess.DEVNULL,
            cwd="/", env=dict(_LAUNCHD_ENVIRONMENT))
    except Exception:
        raise _refuse("SERVICE_RUNTIME_PROVENANCE_UNAVAILABLE") from None
    chunks = []
    consumed = 0
    refusal = ""
    payload = b""
    try:
        try:
            if process.stdout is None:
                raise _refuse("SERVICE_RUNTIME_PROVENANCE_UNAVAILABLE")
            descriptor = process.stdout.fileno()
            os.set_blocking(descriptor, False)
            with selectors.DefaultSelector() as selector:
                selector.register(descriptor, selectors.EVENT_READ)
                while True:
                    budget.check()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise _refuse("SERVICE_QUALIFICATION_BUDGET_EXCEEDED")
                    cap = max_bytes + 1 - consumed
                    if cap <= 0:
                        raise _refuse("SERVICE_LAUNCHCTL_OUTPUT_TOO_LARGE")
                    if not selector.select(min(remaining, _LAUNCHD_POLL_SECONDS)):
                        continue
                    try:
                        block = os.read(descriptor, min(_LAUNCHD_READ_CHUNK_BYTES, cap))
                    except BlockingIOError:
                        continue
                    if not block:
                        break
                    consumed += len(block)
                    if consumed > max_bytes:
                        raise _refuse("SERVICE_LAUNCHCTL_OUTPUT_TOO_LARGE")
                    chunks.append(block)
            code = _reap_bounded_exit_code(process, deadline)
            if code is None:
                raise _refuse("SERVICE_QUALIFICATION_BUDGET_EXCEEDED")
            if code != 0:
                raise _refuse("SERVICE_RUNTIME_PROVENANCE_UNAVAILABLE")
            payload = b"".join(chunks)
            if not payload and not allow_empty:
                raise _refuse("SERVICE_RUNTIME_PROVENANCE_UNAVAILABLE")
        except PeerIdentityError as error:
            refusal = error.code
        except Exception:
            refusal = "SERVICE_RUNTIME_PROVENANCE_UNAVAILABLE"
    finally:
        if not _discard_bounded_child(process):
            refusal = "SERVICE_LAUNCHCTL_CLEANUP_UNPROVEN"
    if refusal:
        raise _refuse(refusal)
    budget.check()
    return payload


def _inventory_python_base(budget: _Budget) -> tuple:
    """Check every import-tree object, including known internal relative links."""
    pending = [("", _PYTHON_BASE)]
    identities = []
    links = []
    total = 0
    while pending:
        budget.check()
        relative, path = pending.pop()
        if len(identities) >= _MAX_WALK_ENTRIES:
            raise _refuse("SERVICE_RUNTIME_ENTRY_LIMIT")
        expected_link = _PYTHON_LINK_INDEX.get(relative)
        handle, info, before = _open_trusted(path, budget=budget,
            allow_symlink=relative if expected_link is not None else None)
        try:
            if expected_link is not None:
                target = _readlink(path)
                if target != expected_link or target.startswith("/"):
                    raise _refuse("SERVICE_RUNTIME_LINK_DRIFT")
                target_path = os.path.normpath(os.path.join(os.path.dirname(path), target))
                if not target_path.startswith(_PYTHON_BASE + "/"):
                    raise _refuse("SERVICE_RUNTIME_LINK_ESCAPES_BASE")
                links.append((relative, target, _object_identity(info)))
            elif stat.S_ISDIR(info.st_mode):
                names = _directory_entries(path, budget)
                if len(identities) + len(pending) + len(names) > _MAX_WALK_ENTRIES:
                    raise _refuse("SERVICE_RUNTIME_ENTRY_LIMIT")
                for name in names:
                    child = relative + "/" + name if relative else name
                    pending.append((child, path + "/" + name))
            elif stat.S_ISREG(info.st_mode):
                if info.st_nlink != 1 or info.st_size > _MAX_READ_BYTES:
                    raise _refuse("SERVICE_RUNTIME_FILE_UNQUALIFIED")
                total += info.st_size
                if total > 512 * 1024 * 1024:
                    raise _refuse("SERVICE_RUNTIME_BYTE_LIMIT")
            else:
                raise _refuse("SERVICE_RUNTIME_BASE_UNQUALIFIED")
            if _object_identity(_lstat(path)) != _object_identity(before):
                raise _refuse("SERVICE_RUNTIME_CHANGED")
            identities.append((relative, _object_identity(info)))
        finally:
            _close(handle)
            budget.check()
    if {name for name, _, _ in links} != set(_PYTHON_LINK_INDEX):
        raise _refuse("SERVICE_RUNTIME_LINK_SET_DRIFT")
    return tuple(sorted(identities)), tuple(sorted(links))


def _verify_python_runtime(budget: _Budget) -> _RuntimeObservation:
    ancestors = _observe_ancestors(_PYTHON_BASE, budget)
    identities, links = _inventory_python_base(budget)
    digests = []
    for path, expected in ((_PYTHON_LAUNCHER, _PYTHON_LAUNCHER_SHA256),
                           (_PYTHON_DYLIB, _PYTHON_DYLIB_SHA256),
                           (_PYTHON_MAIN_EXECUTABLE, _PYTHON_MAIN_SHA256)):
        data, _ = _read_trusted_bytes(path, budget=budget, maximum=_MAX_READ_BYTES,
                                      expected_mode=0o755)
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected:
            raise _refuse("SERVICE_RUNTIME_DIGEST_MISMATCH")
        digests.append(digest)
    patch, _ = _read_trusted_bytes(_PYTHON_PATCHLEVEL, budget=budget, maximum=262144)
    if re.search((r'PY_VERSION\s+"' + re.escape(_PYTHON_VERSION) + r'"').encode("ascii"), patch) is None:
        raise _refuse("SERVICE_RUNTIME_VERSION_MISMATCH")
    _run_bounded_readonly(_CODESIGN_VERIFY_ARGV, budget=budget, max_bytes=4096,
                          allow_empty=True, merge_stderr=False)
    metadata = _run_bounded_readonly(_CODESIGN_METADATA_ARGV, budget=budget, max_bytes=65536,
                                    allow_empty=False, merge_stderr=True)
    teams = re.findall(rb"(?m)^TeamIdentifier=([^\r\n]+)$", metadata)
    flags = re.findall(rb"flags=0x([0-9a-fA-F]+)\(", metadata)
    if (teams != [_PYTHON_TEAM_IDENTIFIER.encode("ascii")] or len(flags) != 1
        or not int(flags[0], 16) & 0x10000 or b"get-task-allow" in metadata):
        raise _refuse("SERVICE_RUNTIME_SIGNATURE_UNQUALIFIED")
    result = _RuntimeObservation(digests[0], digests[1], digests[2], identities, links, ancestors)
    _recheck_python_runtime(result, budget)
    return result


def _recheck_python_runtime(before: _RuntimeObservation, budget: _Budget) -> None:
    if _observe_ancestors(_PYTHON_BASE, budget) != before.ancestor_identities:
        raise _refuse("SERVICE_ANCESTOR_CHANGED")
    identities, links = _inventory_python_base(budget)
    if identities != before.identities or links != before.link_identities:
        raise _refuse("SERVICE_RUNTIME_CHANGED")
    for path, expected in ((_PYTHON_LAUNCHER, before.launcher_digest),
                           (_PYTHON_DYLIB, before.dylib_digest),
                           (_PYTHON_MAIN_EXECUTABLE, before.main_digest)):
        data, _ = _read_trusted_bytes(path, budget=budget, maximum=_MAX_READ_BYTES,
                                     expected_mode=0o755)
        if hashlib.sha256(data).hexdigest() != expected:
            raise _refuse("SERVICE_RUNTIME_CHANGED")
    budget.check()


_CLOSURE_ROW_LIMIT = 4096


def _walk_closure(
    root: str, budget: _Budget, *, hash_files: bool = True
) -> tuple:
    """Inventory one closed runtime tree in the pinned row encoding."""
    rows = []
    identities = []
    total = 0
    files = 0
    directories = 0

    def record(relative: str, path: str) -> None:
        nonlocal total, files, directories
        if len(rows) >= _CLOSURE_ROW_LIMIT:
            raise _refuse("SERVICE_CLOSURE_ENTRY_LIMIT")
        handle, info, _before = _open_trusted(path, budget=budget)
        _close(handle)
        if info.st_nlink != 1 and stat.S_ISREG(info.st_mode):
            raise _refuse("SERVICE_OBJECT_MULTILINK")
        mode = stat.S_IMODE(info.st_mode)
        if stat.S_ISDIR(info.st_mode):
            directories += 1
            rows.append(
                {
                    "path": relative,
                    "kind": "dir",
                    "mode": mode,
                    "uid": info.st_uid,
                    "gid": info.st_gid,
                    "size": info.st_size,
                }
            )
            identities.append((relative, _object_identity(info)))
            for name in _directory_entries(path, budget):
                record(
                    relative + "/" + name if relative != "." else name,
                    path + "/" + name,
                )
            return
        if not stat.S_ISREG(info.st_mode):
            raise _refuse("SERVICE_CLOSURE_OBJECT_UNSUPPORTED")
        files += 1
        digest = ""
        if hash_files:
            data, read_info = _read_trusted_bytes(
                path, budget=budget, maximum=_MAX_READ_BYTES
            )
            if _object_identity(read_info) != _object_identity(info):
                raise _refuse("SERVICE_CLOSURE_CHANGED")
            total += len(data)
            if total > _MAX_CLOSURE_BYTES:
                raise _refuse("SERVICE_CLOSURE_BYTE_LIMIT")
            digest = hashlib.sha256(data).hexdigest()
            size = len(data)
        else:
            size = info.st_size
            total += size
            if total > _MAX_CLOSURE_BYTES:
                raise _refuse("SERVICE_CLOSURE_BYTE_LIMIT")
        rows.append(
            {
                "path": relative,
                "kind": "file",
                "mode": mode,
                "uid": info.st_uid,
                "gid": info.st_gid,
                "size": size,
                "sha256": digest,
            }
        )
        identities.append((relative, _object_identity(info)))

    record(".", root)
    return tuple(rows), tuple(identities), files, directories, total


def _closure_digest(rows: tuple) -> str:
    """Reproduce the pinned aggregate encoding exactly; no re-baselining."""
    ordered = sorted(rows, key=lambda row: row["path"])
    document = {
        "schema": _NETWORK_CLOSURE_SCHEMA,
        "network_lock_sha256": _NETWORK_RUNTIME_NAME,
        "entries": [dict(row) for row in ordered],
    }
    canonical = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(_NETWORK_CLOSURE_DOMAIN + b"\0" + canonical).hexdigest()


@dataclass(frozen=True, slots=True)
class _ClosureObservation:
    aggregate: str
    root_identity: tuple
    ancestor_identities: tuple
    identities: tuple


def _verify_network_closure(budget: _Budget) -> _ClosureObservation:
    ancestors = _observe_ancestors(_NETWORK_RUNTIME_ROOT, budget)
    handle, root_info, _before = _open_trusted(_NETWORK_RUNTIME_ROOT, budget=budget)
    _close(handle)
    if not stat.S_ISDIR(root_info.st_mode):
        raise _refuse("SERVICE_CLOSURE_UNQUALIFIED")
    rows, identities, files, directories, total = _walk_closure(
        _NETWORK_RUNTIME_ROOT, budget
    )
    if files != _NETWORK_CLOSURE_FILE_COUNT:
        raise _refuse("SERVICE_CLOSURE_FILE_COUNT_MISMATCH")
    if directories != _NETWORK_CLOSURE_DIRECTORY_COUNT:
        raise _refuse("SERVICE_CLOSURE_DIRECTORY_COUNT_MISMATCH")
    if total != _NETWORK_CLOSURE_TOTAL_BYTES:
        raise _refuse("SERVICE_CLOSURE_BYTE_COUNT_MISMATCH")
    aggregate = _closure_digest(rows)
    if aggregate != _NETWORK_CLOSURE_PIN_SHA256:
        raise _refuse("SERVICE_CLOSURE_DIGEST_MISMATCH")
    return _ClosureObservation(
        aggregate=aggregate,
        root_identity=_object_identity(root_info),
        ancestor_identities=ancestors,
        identities=identities,
    )


def _recheck_network_closure(before: _ClosureObservation, budget: _Budget) -> None:
    if _observe_ancestors(_NETWORK_RUNTIME_ROOT, budget) != before.ancestor_identities:
        raise _refuse("SERVICE_ANCESTOR_CHANGED")
    handle, root_info, _before = _open_trusted(_NETWORK_RUNTIME_ROOT, budget=budget)
    _close(handle)
    if _object_identity(root_info) != before.root_identity:
        raise _refuse("SERVICE_CLOSURE_CHANGED")
    _rows, identities, _files, _dirs, _total = _walk_closure(
        _NETWORK_RUNTIME_ROOT, budget, hash_files=False
    )
    if identities != before.identities:
        raise _refuse("SERVICE_CLOSURE_CHANGED")
    if before.aggregate != _NETWORK_CLOSURE_PIN_SHA256:
        raise _refuse("SERVICE_CLOSURE_DIGEST_MISMATCH")


def _owner_binding(peer, observation):
    """Sole call site of the A2 owner composition seam in this module."""
    return _peer_identity._bind_qualified_owner_observation(
        _peer_identity._OWNER_CAPABILITY, peer=peer, observation=observation
    )


def _joined(first, second, code: str):
    if first != second:
        raise _refuse(code)
    return second


def _qualify(topology: _RoleTopology, peer, role: str, budget: _Budget):
    budget.check()
    if peer.euid != topology.service_uid:
        raise _refuse("SERVICE_SERVICE_UID_MISMATCH")
    if peer.pid < 1 or peer.pidversion < 1:
        raise _refuse("SERVICE_PEER_IDENTITY_INCOMPLETE")

    boot = _observe_real_boot_id()
    launchd = _observe_launchd_service(role)
    if launchd.pid != peer.pid:
        raise _refuse("SERVICE_LAUNCHD_PID_MISMATCH")
    if launchd.username != topology.username or launchd.group != topology.group:
        raise _refuse("SERVICE_LAUNCHD_IDENTITY_MISMATCH")
    if launchd.program != topology.launcher:
        raise _refuse("SERVICE_LAUNCHD_PROGRAM_MISMATCH")

    plist = _verify_role_plist(topology, budget)
    release_path = _release_directory(plist.release)
    if launchd.argv != plist.argv:
        raise _refuse("SERVICE_LAUNCHD_ARGV_MISMATCH")
    if launchd.working_directory != release_path:
        raise _refuse("SERVICE_PLIST_WORKING_DIRECTORY_MISMATCH")

    config = _verify_role_config(topology, plist.release, budget)
    budget.check()
    projection = _verify_control_projection(budget)
    budget.check()
    if topology.role == "control" and projection.release != plist.release:
        raise _refuse("SERVICE_CONFIG_RELEASE_MISMATCH")
    release = _verify_release(topology, plist.release, budget)
    budget.check()
    runtime = _verify_python_runtime(budget)
    budget.check()
    closure = _verify_network_closure(budget) if topology.network_closure else None
    budget.check()
    dynamic = _observe_dynamic_code(peer.audit_token, _PYTHON_MAIN_EXECUTABLE)
    budget.check()
    if (
        dynamic.dynamic_code_status != 0
        or dynamic.executable_path != _PYTHON_MAIN_EXECUTABLE
    ):
        raise _refuse("SERVICE_DYNAMIC_CODE_NOT_VALID")

    # Race joins: every identity used above must still hold right now, with no
    # positive cache anywhere in this factory.
    _joined(_observe_real_boot_id(), boot, "SERVICE_BOOT_ID_CHANGED")
    _joined(_observe_launchd_service(role), launchd, "SERVICE_LAUNCHD_CHANGED")
    _joined(
        _observe_dynamic_code(peer.audit_token, _PYTHON_MAIN_EXECUTABLE),
        dynamic,
        "SERVICE_DYNAMIC_CODE_CHANGED",
    )
    _joined(
        _verify_role_plist(topology, budget, expected_release=plist.release),
        plist,
        "SERVICE_PLIST_CHANGED",
    )
    _joined(
        _verify_role_config(topology, plist.release, budget),
        config,
        "SERVICE_CONFIG_CHANGED",
    )
    _joined(_verify_control_projection(budget), projection, "SERVICE_CONFIG_CHANGED")
    budget.check()
    _recheck_release(release, budget)
    _recheck_python_runtime(runtime, budget)
    if closure is not None:
        _recheck_network_closure(closure, budget)

    _joined(_verify_role_plist(topology, budget, expected_release=plist.release), plist, "SERVICE_PLIST_CHANGED")
    _joined(_verify_role_config(topology, plist.release, budget), config, "SERVICE_CONFIG_CHANGED")
    _joined(_verify_control_projection(budget), projection, "SERVICE_CONFIG_CHANGED")
    _joined(_observe_real_boot_id(), boot, "SERVICE_BOOT_ID_CHANGED")
    _joined(_observe_launchd_service(role), launchd, "SERVICE_LAUNCHD_CHANGED")
    _joined(_observe_dynamic_code(peer.audit_token, _PYTHON_MAIN_EXECUTABLE), dynamic, "SERVICE_DYNAMIC_CODE_CHANGED")
    budget.check()
    state = _peer_identity._current_capture(peer)
    if state.original.audit_token != peer.audit_token or state.receiver_pid != os.getpid():
        raise _refuse("SERVICE_PEER_IDENTITY_MISMATCH")

    return _peer_identity._QualifiedOwnerObservation(
        real_boot_id=boot,
        audit_identity_digest=peer.audit_identity_digest,
        service_label=launchd.service_label,
        installed_release=plist.release,
        config_digest=config.digest,
        connection_instance=peer.connection_instance,
        euid=peer.euid,
        pid=peer.pid,
        pidversion=peer.pidversion,
        plist_path=launchd.plist_path,
        plist_uid=0,
        service_uid=topology.service_uid,
        argv=launchd.argv,
        python_provenance_digest=projection.provenance_digest,
        wrapper_digest=release.wrapper_digest,
        designated_requirement_digest=dynamic.designated_requirement_digest,
        dynamic_code_identity_digest=dynamic.dynamic_code_identity_digest,
        dynamic_code_status=dynamic.dynamic_code_status,
    )


def qualify_installed_peer(peer, *, role):
    """Qualify one live installed-service peer for one closed role.

    Only a genuine A2 kernel capture and a closed literal role are accepted: no
    caller pin, path, PID, label, argv, config, injected callback, or approval
    switch is honoured. Every observation is re-taken fresh inside one monotonic
    budget, and an A2 installed-service binding is composed only when the real
    boot session, launchd account, trusted plist, role config, Python provenance
    projection, exact-SHA release closure, signed PSF runtime, gateway network
    closure, and dynamic code identity all agree before and after. Any refusal
    carries one short nonsecret code and never a path, config, or exception text.
    """
    try:
        topology = _role_topology(role)
        budget = _Budget(_SERVICE_BUDGET_SECONDS)
        capture = _peer_identity._current_capture(peer)
        if type(capture) is not _peer_identity._CaptureState:
            raise _refuse("PEER_CAPTURE_PROVENANCE_REQUIRED")
        observation = _qualify(topology, peer, role, budget)
        budget.check()
        binding = _owner_binding(peer, observation)
        budget.check()
        if binding is None or type(binding) is not _peer_identity.InstalledServicePeerBinding:
            raise _refuse("SERVICE_OWNER_BINDING_REQUIRED")
        return binding
    except PeerIdentityError:
        raise
    except Exception:
        raise _refuse("SERVICE_QUALIFICATION_UNAVAILABLE") from None
