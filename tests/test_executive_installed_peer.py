"""Mocked Darwin security-bridge mechanics; live qualification is unproven."""

from __future__ import annotations

import ctypes
import hashlib
from pathlib import Path

import pytest

from control_plane import executive_installed_peer as installed
from control_plane import executive_peer_identity as peer


EXPECTED = "/fixed/control.py"
AUDIT = b"K" * 32
UNIQUE = b"\xab" * 32
REQUIREMENT_BLOB = b"designated-requirement-blob"
BUNDLE = "/fixed/Python.app"
BUNDLE_EXE = "/fixed/Python.app/Contents/MacOS/Python"

_DATA_TYPE = 101
_URL_TYPE = 102
_DICT_TYPE = 103
_OTHER_TYPE = 199

_CONSTANTS = frozenset({1, 2, 3, 4, 5})


def _identity_digest(audit: bytes, unique: bytes, path: str) -> str:
    path_bytes = path.encode("utf-8")
    hasher = hashlib.sha256()
    for part in (audit, unique, path_bytes):
        hasher.update(len(part).to_bytes(8, "big"))
        hasher.update(part)
    return hasher.hexdigest()


def _read_buffer(buf, length: int) -> bytes:
    return bytes(bytearray(buf[i] for i in range(length)))


class FakeSecurity:
    """In-process CF/Security stand-in. No live Darwin invocation."""

    def __init__(self, **plan):
        self.plan = plan
        self.next_id = 100
        self.objects: dict[int, dict] = {}
        self.created: list[int] = []
        self.borrowed: list[int] = []
        self.releases: list[int] = []
        self.calls: list[tuple] = []
        self.keepalive: list[object] = []
        self.kSecGuestAttributeAudit = 1
        self.kSecCodeInfoUnique = 2
        self.kSecCodeInfoMainExecutable = 5
        self.kCFTypeDictionaryKeyCallBacks = 3
        self.kCFTypeDictionaryValueCallBacks = 4

    def _alloc(self, kind: str, type_id: int, **meta) -> int:
        ref = self.next_id
        self.next_id += 1
        self.objects[ref] = {"kind": kind, "type_id": type_id, **meta}
        self.created.append(ref)
        return ref

    def _store(self, out, value: int) -> None:
        ctypes.cast(out, ctypes.POINTER(ctypes.c_void_p))[0] = value

    def _borrow(self, meta: dict) -> int:
        ref = self.next_id
        self.next_id += 1
        self.objects[ref] = meta
        self.borrowed.append(ref)
        return ref

    def _borrowed_cfdata(self, spec) -> int:
        if spec is None:
            return None
        if spec == "wrong-type":
            return self._borrow(
                {"kind": "wrong", "type_id": _OTHER_TYPE, "blob": b"x"}
            )
        ref = self._borrow({"kind": "data", "type_id": _DATA_TYPE, "blob": spec})
        if self.plan.get("unique_null_bytes"):
            self.objects[ref]["null_bytes"] = True
        if self.plan.get("unique_length_override") is not None:
            self.objects[ref]["length_override"] = self.plan["unique_length_override"]
        return ref

    def _borrowed_url(self, spec) -> int:
        if spec is None:
            return None
        if spec == "wrong-type":
            return self._borrow(
                {"kind": "wrong", "type_id": _OTHER_TYPE, "path": "/fixed/not-a-url"}
            )
        meta = {"kind": "url", "type_id": _URL_TYPE}
        if isinstance(spec, bytes):
            meta["raw"] = spec
        else:
            meta["path"] = spec
        ref = self._borrow(meta)
        if self.plan.get("main_decode_fail"):
            self.objects[ref]["decode_fail"] = True
        return ref

    def CFDataCreate(self, allocator, buf, length):
        blob = _read_buffer(buf, int(length))
        self.calls.append(("CFDataCreate", allocator, blob, int(length)))
        if self.plan.get("data_create_null"):
            return None
        return self._alloc("data", _DATA_TYPE, blob=blob)

    def CFDataGetLength(self, ref):
        self.calls.append(("CFDataGetLength", ref))
        obj = self.objects[int(ref)]
        if "length_override" in obj:
            return obj["length_override"]
        return len(obj["blob"])

    def CFDataGetBytePtr(self, ref):
        self.calls.append(("CFDataGetBytePtr", ref))
        obj = self.objects[int(ref)]
        if obj.get("null_bytes"):
            return None
        blob = obj["blob"]
        buf = ctypes.create_string_buffer(blob, len(blob))
        self.keepalive.append(buf)
        return ctypes.addressof(buf)

    def CFDataGetTypeID(self):
        return _DATA_TYPE

    def CFDictionaryCreate(self, allocator, keys, values, n, key_cb, value_cb):
        key = int(keys[0]) if n else None
        value = int(values[0]) if n else None
        self.calls.append(
            ("CFDictionaryCreate", allocator, key, value, int(n), key_cb, value_cb)
        )
        if self.plan.get("dict_create_null"):
            return None
        return self._alloc(
            "dict",
            _DICT_TYPE,
            key=key,
            value=value,
            key_cb=key_cb,
            value_cb=value_cb,
        )

    def CFDictionaryGetValue(self, dictionary, key):
        self.calls.append(("CFDictionaryGetValue", dictionary, key))
        obj = self.objects[int(dictionary)]
        key = int(key)
        if key == self.kSecCodeInfoUnique:
            return obj.get("unique_ref")
        if key == self.kSecCodeInfoMainExecutable:
            return obj.get("main_executable_ref")
        return None

    def CFDictionaryGetTypeID(self):
        return _DICT_TYPE

    def CFURLCreateFromFileSystemRepresentation(self, allocator, buf, length, is_dir):
        blob = _read_buffer(buf, int(length))
        self.calls.append(
            (
                "CFURLCreateFromFileSystemRepresentation",
                allocator,
                blob,
                int(length),
                int(is_dir),
            )
        )
        if self.plan.get("url_create_null"):
            return None
        return self._alloc(
            "url", _URL_TYPE, path=blob.decode("ascii"), is_dir=int(is_dir)
        )

    def CFURLGetFileSystemRepresentation(self, url, resolve, buffer, max_len):
        self.calls.append(
            (
                "CFURLGetFileSystemRepresentation",
                url,
                int(resolve),
                int(max_len),
            )
        )
        obj = self.objects[int(url)]
        raw = obj["raw"] if "raw" in obj else obj["path"].encode("utf-8") + b"\0"
        if obj.get("decode_fail") or len(raw) > int(max_len):
            return 0
        for index, byte in enumerate(raw):
            buffer[index] = byte
        return 1

    def CFURLGetTypeID(self):
        return _URL_TYPE

    def CFGetTypeID(self, ref):
        return self.objects[int(ref)]["type_id"]

    def CFRelease(self, ref):
        value = int(ref)
        self.releases.append(value)
        self.calls.append(("CFRelease", value))

    def SecCodeCopySelf(self, *args):
        self.calls.append(("SecCodeCopySelf", args))
        raise AssertionError("SecCodeCopySelf must not be used")

    def SecCodeCreateWithPID(self, *args):
        self.calls.append(("SecCodeCreateWithPID", args))
        raise AssertionError("SecCodeCreateWithPID must not be used")

    def SecCodeCreateWithAuditToken(self, *args):
        self.calls.append(("SecCodeCreateWithAuditToken", args))
        raise AssertionError("SecCodeCreateWithAuditToken must not be used")

    def SecCodeCopyGuestWithAttributes(self, host, attributes, flags, out):
        self.calls.append(
            ("SecCodeCopyGuestWithAttributes", host, attributes, int(flags))
        )
        status = self.plan.get("guest_status", 0)
        if status != 0:
            return status
        if self.plan.get("guest_null"):
            return 0
        guest = self._alloc("guest", _OTHER_TYPE)
        self._store(out, guest)
        return 0

    def SecStaticCodeCreateWithPath(self, url, flags, out):
        self.calls.append(("SecStaticCodeCreateWithPath", url, int(flags)))
        status = self.plan.get("static_status", 0)
        if status != 0:
            return status
        if self.plan.get("static_null"):
            return 0
        static = self._alloc("static", _OTHER_TYPE, url=url)
        self._store(out, static)
        return 0

    def SecCodeCopyDesignatedRequirement(self, code, flags, out):
        self.calls.append(("SecCodeCopyDesignatedRequirement", code, int(flags)))
        status = self.plan.get("requirement_status", 0)
        if status != 0:
            return status
        if self.plan.get("requirement_null"):
            return 0
        requirement = self._alloc("requirement", _OTHER_TYPE, code=code)
        self._store(out, requirement)
        return 0

    def SecRequirementCopyData(self, requirement, flags, out):
        self.calls.append(("SecRequirementCopyData", requirement, int(flags)))
        status = self.plan.get("requirement_data_status", 0)
        if status != 0:
            return status
        if self.plan.get("requirement_data_null"):
            return 0
        blob = self.plan.get("requirement_blob", REQUIREMENT_BLOB)
        data = self._alloc("data", _DATA_TYPE, blob=blob)
        self._store(out, data)
        return 0

    def SecCodeCheckValidity(self, code, flags, requirement):
        self.calls.append(("SecCodeCheckValidity", code, int(flags), requirement))
        return self.plan.get("validity_status", 0)

    def SecCodeCopyPath(self, code, flags, out):
        """Bundle-container decoy: differs from the executable by default."""
        self.calls.append(("SecCodeCopyPath", code, int(flags)))
        url = self._alloc(
            "url", _URL_TYPE, path=self.plan.get("container_path", BUNDLE)
        )
        self._store(out, url)
        return 0

    def SecCodeCopySigningInformation(self, code, flags, out):
        self.calls.append(("SecCodeCopySigningInformation", code, int(flags)))
        status = self.plan.get("info_status", 0)
        if status != 0:
            return status
        if self.plan.get("info_null"):
            return 0
        unique_ref = self._borrowed_cfdata(self.plan.get("unique", UNIQUE))
        main_ref = self._borrowed_url(self.plan.get("main_executable", EXPECTED))
        info = self._alloc(
            "dict", _DICT_TYPE, unique_ref=unique_ref, main_executable_ref=main_ref
        )
        if self.plan.get("info_wrong_type"):
            self.objects[info]["type_id"] = _OTHER_TYPE
        self._store(out, info)
        return 0


@pytest.fixture
def fake(monkeypatch):
    security = FakeSecurity()
    monkeypatch.setattr(installed, "_darwin_security_api", lambda: security)
    return security


def observe(security=None):
    return installed._observe_dynamic_code(AUDIT, EXPECTED)


def test_public_qualify_unconditionally_incomplete_and_never_binds(
    fake, monkeypatch
):
    bound = []
    observed = []
    monkeypatch.setattr(
        peer,
        "_bind_qualified_owner_observation",
        lambda *args, **kwargs: bound.append((args, kwargs)),
    )
    original = installed._observe_dynamic_code

    def wrapped(*args, **kwargs):
        observed.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(installed, "_observe_dynamic_code", wrapped)
    with pytest.raises(peer.PeerIdentityError) as caught:
        installed.qualify_installed_peer(object(), role="control")
    assert caught.value.code == "SERVICE_INSTALLATION_QUALIFICATION_INCOMPLETE"
    assert bound == []
    assert observed == []
    assert "raw" not in str(caught.value)
    assert EXPECTED not in str(caught.value)


def test_public_surface_has_no_positive_qualification_path():
    assert installed.__all__ == ["qualify_installed_peer"]
    source = Path(installed.__file__).read_text(encoding="ascii")
    for banned in (
        "SecCodeCopySelf",
        "SecCodeCreateWithPID",
        "SecCodeCreateWithAuditToken",
        "getpeereid",
        "_bind_qualified_owner_observation",
        "_OWNER_CAPABILITY",
    ):
        assert banned not in source


@pytest.mark.parametrize(
    "raw", [b"", b"\0" * 31, b"\0" * 33, bytearray(32), None, "x" * 32, 32]
)
def test_audit_token_requires_exact_opaque_kernel_size(raw):
    with pytest.raises(peer.PeerIdentityError) as caught:
        installed._observe_dynamic_code(raw, EXPECTED)
    assert caught.value.code == "PEER_AUDIT_TOKEN_INVALID"
    assert EXPECTED not in str(caught.value)


@pytest.mark.parametrize(
    "path",
    [
        None,
        True,
        1,
        "",
        "relative/control.py",
        "/path/../control.py",
        "/path//control.py",
        "/path/./control.py",
        "/trailing/",
        "/x\n",
        "/caf\u00e9",
        "/x" * 5000,
    ],
)
def test_expected_executable_must_be_absolute_and_exact(path):
    with pytest.raises(peer.PeerIdentityError) as caught:
        installed._observe_dynamic_code(AUDIT, path)
    assert caught.value.code == "SERVICE_EXPECTED_EXECUTABLE_INVALID"
    assert AUDIT not in str(caught.value).encode() if isinstance(AUDIT, bytes) else True


def test_unsupported_platform_has_no_pid_or_self_fallback(monkeypatch):
    monkeypatch.setattr(installed.sys, "platform", "linux")
    installed._darwin_security_api.cache_clear()
    with pytest.raises(peer.PeerIdentityError) as caught:
        installed._observe_dynamic_code(AUDIT, EXPECTED)
    assert caught.value.code == "PEER_PLATFORM_UNSUPPORTED"


@pytest.mark.parametrize("missing", ["library", "symbol"])
def test_missing_security_api_fails_closed_without_fallback(monkeypatch, missing):
    monkeypatch.setattr(installed.sys, "platform", "darwin")
    installed._darwin_security_api.cache_clear()

    def unavailable(_path):
        if missing == "library":
            raise OSError("not installed")
        return object()

    monkeypatch.setattr(installed.ctypes, "CDLL", unavailable)
    with pytest.raises(peer.PeerIdentityError) as caught:
        installed._darwin_security_api.__wrapped__()
    assert caught.value.code == "SERVICE_CODE_SIGNING_API_UNAVAILABLE"


def test_audit_bytes_feed_cfdata_and_guest_dictionary(fake):
    result = observe()
    creates = [call for call in fake.calls if call[0] == "CFDataCreate"]
    assert creates[0][2] == AUDIT
    assert creates[0][3] == 32
    dict_calls = [call for call in fake.calls if call[0] == "CFDictionaryCreate"]
    assert len(dict_calls) == 1
    _, allocator, key, value, n, key_cb, value_cb = dict_calls[0]
    assert allocator is None
    assert key == fake.kSecGuestAttributeAudit
    assert n == 1
    assert key_cb == fake.kCFTypeDictionaryKeyCallBacks
    assert value_cb == fake.kCFTypeDictionaryValueCallBacks
    assert value in fake.objects
    assert fake.objects[value]["blob"] == AUDIT
    guest_calls = [
        call for call in fake.calls if call[0] == "SecCodeCopyGuestWithAttributes"
    ]
    attributes_ref = next(
        ref for ref in fake.created if fake.objects[ref]["kind"] == "dict"
    )
    assert guest_calls == [
        ("SecCodeCopyGuestWithAttributes", None, attributes_ref, 0)
    ]
    assert fake.objects[attributes_ref]["key"] == fake.kSecGuestAttributeAudit
    assert fake.objects[attributes_ref]["value"] == value
    assert result.dynamic_code_status == 0
    assert result.executable_path == EXPECTED


def test_guest_lookup_does_not_fall_back_to_pid_or_self(fake, monkeypatch):
    fake.plan["guest_status"] = -67065
    with pytest.raises(peer.PeerIdentityError) as caught:
        observe()
    assert caught.value.code == "SERVICE_DYNAMIC_GUEST_UNAVAILABLE"
    names = [call[0] for call in fake.calls]
    assert "SecCodeCopySelf" not in names
    assert "SecCodeCreateWithPID" not in names
    assert "SecCodeCreateWithAuditToken" not in names
    assert "SecStaticCodeCreateWithPath" not in names


def test_expected_requirement_is_passed_into_dynamic_validity(fake):
    result = observe()
    static_calls = [
        call for call in fake.calls if call[0] == "SecStaticCodeCreateWithPath"
    ]
    req_calls = [
        call for call in fake.calls if call[0] == "SecCodeCopyDesignatedRequirement"
    ]
    validity = [call for call in fake.calls if call[0] == "SecCodeCheckValidity"]
    guest_calls = [
        call for call in fake.calls if call[0] == "SecCodeCopyGuestWithAttributes"
    ]
    assert static_calls[0][2] == 0
    static_ref = next(
        ref for ref in fake.created if fake.objects[ref]["kind"] == "static"
    )
    assert req_calls[0][1] == static_ref
    requirement = next(
        ref for ref in fake.created if fake.objects[ref]["kind"] == "requirement"
    )
    guest = next(ref for ref in fake.created if fake.objects[ref]["kind"] == "guest")
    assert validity == [("SecCodeCheckValidity", guest, 0, requirement)]
    assert guest_calls[0][1] is None
    info_calls = [
        call for call in fake.calls if call[0] == "SecCodeCopySigningInformation"
    ]
    assert info_calls == [("SecCodeCopySigningInformation", guest, 0)]
    url_calls = [
        call
        for call in fake.calls
        if call[0] == "CFURLCreateFromFileSystemRepresentation"
    ]
    assert url_calls[0][2] == EXPECTED.encode("ascii")
    assert url_calls[0][4] == 0
    assert result.designated_requirement_digest == hashlib.sha256(
        REQUIREMENT_BLOB
    ).hexdigest()


@pytest.mark.parametrize(
    "plan,code",
    [
        ({"guest_status": 1}, "SERVICE_DYNAMIC_GUEST_UNAVAILABLE"),
        ({"guest_null": True}, "SERVICE_DYNAMIC_GUEST_UNAVAILABLE"),
        ({"dict_create_null": True}, "SERVICE_DYNAMIC_GUEST_UNAVAILABLE"),
        ({"data_create_null": True}, "SERVICE_CODE_SIGNING_API_UNAVAILABLE"),
        ({"url_create_null": True}, "SERVICE_STATIC_CODE_UNAVAILABLE"),
        ({"static_status": 2}, "SERVICE_STATIC_CODE_UNAVAILABLE"),
        ({"static_null": True}, "SERVICE_STATIC_CODE_UNAVAILABLE"),
        ({"requirement_status": 3}, "SERVICE_DESIGNATED_REQUIREMENT_UNAVAILABLE"),
        ({"requirement_null": True}, "SERVICE_DESIGNATED_REQUIREMENT_UNAVAILABLE"),
        (
            {"requirement_data_status": 4},
            "SERVICE_DESIGNATED_REQUIREMENT_UNAVAILABLE",
        ),
        ({"requirement_data_null": True}, "SERVICE_DESIGNATED_REQUIREMENT_UNAVAILABLE"),
        ({"validity_status": -67050}, "SERVICE_DYNAMIC_CODE_NOT_VALID"),
        ({"validity_status": 1}, "SERVICE_DYNAMIC_CODE_NOT_VALID"),
        ({"main_executable": None}, "SERVICE_CODE_IDENTITY_MALFORMED"),
        ({"main_executable": "wrong-type"}, "SERVICE_CODE_IDENTITY_MALFORMED"),
        ({"main_executable": ""}, "SERVICE_DYNAMIC_CODE_PATH_UNAVAILABLE"),
        ({"main_executable": b"/x" * 2048}, "SERVICE_DYNAMIC_CODE_PATH_UNAVAILABLE"),
        ({"main_executable": b"/fixed/\xff\xfe-bytes"},
         "SERVICE_DYNAMIC_CODE_PATH_UNAVAILABLE"),
        ({"main_executable": "/x" * 5000}, "SERVICE_DYNAMIC_CODE_PATH_UNAVAILABLE"),
        ({"main_decode_fail": True}, "SERVICE_DYNAMIC_CODE_PATH_UNAVAILABLE"),
        ({"main_executable": "/fixed/other.py"}, "SERVICE_EXECUTABLE_PATH_MISMATCH"),
        ({"info_status": 6}, "SERVICE_CODE_IDENTITY_UNAVAILABLE"),
        ({"info_null": True}, "SERVICE_CODE_IDENTITY_UNAVAILABLE"),
        ({"info_wrong_type": True}, "SERVICE_CODE_IDENTITY_MALFORMED"),
        ({"unique": None}, "SERVICE_CODE_IDENTITY_MALFORMED"),
        ({"unique": "wrong-type"}, "SERVICE_CODE_IDENTITY_MALFORMED"),
        ({"unique": b""}, "SERVICE_CODE_IDENTITY_MALFORMED"),
        ({"unique": b"U" * 65}, "SERVICE_CODE_IDENTITY_MALFORMED"),
        ({"unique_null_bytes": True}, "SERVICE_CODE_IDENTITY_MALFORMED"),
        ({"unique_length_override": 0}, "SERVICE_CODE_IDENTITY_MALFORMED"),
        ({"unique_length_override": 10000}, "SERVICE_CODE_IDENTITY_MALFORMED"),
        (
            {"requirement_blob": b"R" * (65536 + 1)},
            "SERVICE_DESIGNATED_REQUIREMENT_UNAVAILABLE",
        ),
    ],
)
def test_nonzero_null_type_and_oversized_outputs_fail_closed(
    monkeypatch, plan, code
):
    security = FakeSecurity(**plan)
    if plan.get("unique") == b"":
        security.plan["unique"] = b""
    monkeypatch.setattr(installed, "_darwin_security_api", lambda: security)
    with pytest.raises(peer.PeerIdentityError) as caught:
        observe()
    assert caught.value.code == code
    assert EXPECTED not in str(caught.value)
    assert "/fixed/other.py" not in str(caught.value)


def test_boolean_validity_status_is_not_success(monkeypatch):
    security = FakeSecurity(validity_status=True)
    monkeypatch.setattr(installed, "_darwin_security_api", lambda: security)
    with pytest.raises(peer.PeerIdentityError) as caught:
        observe()
    assert caught.value.code == "SERVICE_DYNAMIC_CODE_NOT_VALID"


def test_owned_copy_refs_released_once_in_reverse_borrowed_constants_not_released(
    fake,
):
    observe()
    owned = list(fake.created)
    assert fake.releases == list(reversed(owned))
    assert len(fake.releases) == len(set(fake.releases))
    for constant in _CONSTANTS:
        assert constant not in fake.releases
    assert [call[0] for call in fake.calls if call[0] == "SecCodeCopyPath"] == []
    assert BUNDLE not in {fake.objects[ref].get("path") for ref in owned}
    gets = [call for call in fake.calls if call[0] == "CFDictionaryGetValue"]
    assert [call[2] for call in gets] == [
        fake.kSecCodeInfoMainExecutable,
        fake.kSecCodeInfoUnique,
    ]
    info_ref = gets[0][1]
    assert fake.created.count(info_ref) == 1
    assert fake.releases.count(info_ref) == 1
    assert len({call[1] for call in gets}) == 1
    for key in ("main_executable_ref", "unique_ref"):
        borrowed = fake.objects[info_ref][key]
        assert borrowed in fake.borrowed
        assert borrowed not in fake.created
        assert borrowed not in fake.releases


def test_failure_still_releases_acquired_owned_refs_in_reverse(monkeypatch):
    security = FakeSecurity(validity_status=1)
    monkeypatch.setattr(installed, "_darwin_security_api", lambda: security)
    with pytest.raises(peer.PeerIdentityError):
        observe()
    assert security.releases == list(reversed(security.created))
    for constant in _CONSTANTS:
        assert constant not in security.releases


def test_deterministic_identity_binds_audit_code_digest_and_path(
    fake, monkeypatch
):
    result = observe()
    assert result.dynamic_code_status == 0
    assert result.executable_path == EXPECTED
    assert result.designated_requirement_digest == hashlib.sha256(
        REQUIREMENT_BLOB
    ).hexdigest()
    assert result.dynamic_code_identity_digest == _identity_digest(
        AUDIT, UNIQUE, EXPECTED
    )
    other = FakeSecurity(unique=b"\xcd" * 32)
    monkeypatch.setattr(installed, "_darwin_security_api", lambda: other)
    changed = installed._observe_dynamic_code(AUDIT, EXPECTED)
    assert changed.dynamic_code_identity_digest != result.dynamic_code_identity_digest
    monkeypatch.setattr(installed, "_darwin_security_api", lambda: FakeSecurity())
    token_changed = installed._observe_dynamic_code(b"J" * 32, EXPECTED)
    assert (
        token_changed.dynamic_code_identity_digest
        != result.dynamic_code_identity_digest
    )
    path_other = FakeSecurity(main_executable="/fixed/python")
    monkeypatch.setattr(installed, "_darwin_security_api", lambda: path_other)
    path_changed = installed._observe_dynamic_code(AUDIT, "/fixed/python")
    assert (
        path_changed.dynamic_code_identity_digest
        != result.dynamic_code_identity_digest
    )


@pytest.mark.parametrize(
    "observed",
    [
        "/fixed/./control.py",
        "/fixed/../control.py",
        "/fixed/control.py/",
        "/FIXED/control.py",
        "/fixed/control.py ",
        "/fixed/control",
    ],
)
def test_main_executable_comparison_is_exact_not_normalized(monkeypatch, observed):
    security = FakeSecurity(
        main_executable=observed, container_path="/fixed/bundle.app"
    )
    monkeypatch.setattr(installed, "_darwin_security_api", lambda: security)
    with pytest.raises(peer.PeerIdentityError) as caught:
        installed._observe_dynamic_code(AUDIT, EXPECTED)
    assert caught.value.code == "SERVICE_EXECUTABLE_PATH_MISMATCH"


def test_observation_is_immutable(fake):
    result = observe()
    with pytest.raises(AttributeError):
        result.dynamic_code_status = 1
    with pytest.raises(AttributeError):
        result.executable_path = "/elsewhere"


def test_bound_argtypes_match_security_and_corefoundation_headers():
    api = installed._DarwinSecurityAPI()
    # Structural contract of the loader: every Copy out-param is POINTER(c_void_p)
    # and flags are uint32. Exercised via the bound function table on Darwin;
    # here assert the ctypes types the loader will install.
    assert installed._OSStatus is ctypes.c_int32
    assert installed._SecCSFlags is ctypes.c_uint32
    assert installed._Boolean is ctypes.c_ubyte
    assert installed._ERR_SEC_SUCCESS == 0
    assert api.__slots__  # table is closed; no PID helpers
    assert "SecCodeCopySelf" not in api.__slots__
    assert "SecCodeCreateWithPID" not in api.__slots__
    assert "kSecCodeInfoMainExecutable" in api.__slots__
    assert "SecCodeCopyPath" in api.__slots__  # bound ABI, never an identity source


def test_bundle_container_may_differ_from_the_exact_executable(monkeypatch):
    security = FakeSecurity(container_path=BUNDLE, main_executable=BUNDLE_EXE)
    monkeypatch.setattr(installed, "_darwin_security_api", lambda: security)
    result = installed._observe_dynamic_code(AUDIT, BUNDLE_EXE)
    assert result.executable_path == BUNDLE_EXE
    assert result.dynamic_code_identity_digest == _identity_digest(
        AUDIT, UNIQUE, BUNDLE_EXE
    )
    assert [call[0] for call in security.calls if call[0] == "SecCodeCopyPath"] == []


def test_matching_bundle_container_with_wrong_executable_still_refuses(monkeypatch):
    security = FakeSecurity(container_path=EXPECTED, main_executable=BUNDLE_EXE)
    monkeypatch.setattr(installed, "_darwin_security_api", lambda: security)
    with pytest.raises(peer.PeerIdentityError) as caught:
        installed._observe_dynamic_code(AUDIT, EXPECTED)
    assert caught.value.code == "SERVICE_EXECUTABLE_PATH_MISMATCH"
    assert EXPECTED not in str(caught.value)
    assert BUNDLE_EXE not in str(caught.value)
    assert [call[0] for call in security.calls if call[0] == "SecCodeCopyPath"] == []


def test_container_path_is_not_bound_into_the_identity_digest(monkeypatch):
    digests = set()
    for container in (BUNDLE, "/fixed/other.app", "/fixed/control.py"):
        security = FakeSecurity(container_path=container, main_executable=BUNDLE_EXE)
        monkeypatch.setattr(
            installed, "_darwin_security_api", lambda sec=security: sec
        )
        observation = installed._observe_dynamic_code(AUDIT, BUNDLE_EXE)
        digests.add(observation.dynamic_code_identity_digest)
    assert len(digests) == 1
    assert digests == {_identity_digest(AUDIT, UNIQUE, BUNDLE_EXE)}


def test_identity_dictionary_is_not_read_before_dynamic_validity(monkeypatch):
    security = FakeSecurity(validity_status=-67034)
    monkeypatch.setattr(installed, "_darwin_security_api", lambda: security)
    with pytest.raises(peer.PeerIdentityError) as caught:
        installed._observe_dynamic_code(AUDIT, EXPECTED)
    assert caught.value.code == "SERVICE_DYNAMIC_CODE_NOT_VALID"
    names = [call[0] for call in security.calls]
    assert "SecCodeCopySigningInformation" not in names
    assert "CFDictionaryGetValue" not in names


@pytest.mark.parametrize(
    "plan",
    [
        {"main_executable": None},
        {"main_executable": "wrong-type"},
        {"main_executable": b"/x" * 2048},
        {"main_executable": b"/fixed/\xff\xfe-bytes"},
        {"main_executable": "/x" * 5000},
        {"main_decode_fail": True},
        {"main_executable": "/fixed/other.py"},
        {"unique": None},
    ],
)
def test_borrowed_main_url_survives_failures_and_information_releases_once(
    monkeypatch, plan
):
    security = FakeSecurity(**plan)
    monkeypatch.setattr(installed, "_darwin_security_api", lambda: security)
    with pytest.raises(peer.PeerIdentityError):
        installed._observe_dynamic_code(AUDIT, EXPECTED)
    dicts = [ref for ref in security.created if security.objects[ref]["kind"] == "dict"]
    assert len(dicts) == 2
    info_ref = dicts[1]
    assert security.releases == list(reversed(security.created))
    assert security.releases.count(info_ref) == 1
    assert info_ref not in security.borrowed
    main_ref = security.objects[info_ref]["main_executable_ref"]
    if main_ref is not None:
        assert main_ref in security.borrowed
        assert main_ref not in security.created
        assert main_ref not in security.releases
    for constant in _CONSTANTS:
        assert constant not in security.releases


# Launchd's nested diagnostic PID is deliberately different from its service
# PID. These tests establish parsing and bounded IO, not installed authority.
def _launchd_fixture(role='control'):
    label, user = ('com.mastermind.executive.control', '_mastermind_exec') if role == 'control' else ('com.mastermind.executive.mcp', '_mastermind_executive_mcp')
    return (f'system/{label} = {{\n'
            f'\tpath = /Library/LaunchDaemons/{label}.plist\n'
            '\ttype = LaunchDaemon\n\tstate = running\n'
            '\tprogram = /test/python\n\targuments = {\n'
            '\t\t/test/python\n\t\t-I\n\t}\n'
            '\tworking directory = /test/release\n'
            f'\tusername = {user}\n\tgroup = {user}\n'
            '\tdomain = system\n\tpid = 41\n'
            '\tdiagnostics = {\n\t\tpid = 9999\n'
            '\t\tinner = {\n\t\t\tpath = /spoof\n\t\t}\n\t}\n'
            '\tproperties = keepalive | runatload\n}\n').encode()


@pytest.mark.parametrize('role', ['control', 'gateway'])
def test_launchd_observer_parses_root_identity_not_nested_diagnostics(role):
    o = installed._parse_launchctl_service(_launchd_fixture(role), role=role)
    assert o.pid == 41
    assert o.argv == ('/test/python', '-I')
    assert o.plist_path.endswith(o.service_label + '.plist')
    assert o.working_directory == '/test/release'
    with pytest.raises(Exception):
        o.pid = 9999


@pytest.mark.parametrize('old,new', [
    (b'\tpid = 41\n', b''),
    (b'\tpid = 41\n', b'\tpid = 41\n\tpid = 9999\n'),
    (b'\tpid = 41\n', b'\tpid = 041\n'),
    (b'\tpid = 41\n', b'\tpid = 0\n'),
    (b'\tpid = 41\n', b'\tpid = -1\n'),
    (b'\tpid = 41\n', b'\tpid = 2147483648\n'),
    (b'\ttype = LaunchDaemon', b'\ttype = LaunchAgent'),
    (b'\tstate = running', b'\tstate = waiting'),
    (b'\tdomain = system', b'\tdomain = user'),
    (b'\tusername = _mastermind_exec', b'\tusername = attacker'),
    (b'\tgroup = _mastermind_exec', b'\tgroup = attacker'),
    (b'\tpath = /Library/LaunchDaemons/', b'\tpath = /tmp/'),
    (b'\tprogram = /test/python', b'\tprogram = /test/other'),
    (b'\targuments = {', b'\targuments = {\n\t\tinner = {'),
    (b'\t\t-I\n', b'\t\t -I\n'),
    (b'\t\t-I\n', b'\t\t-I \n'),
    (b'\t\t-I\n', b'\t\t-I\x00\n'),
    (b'\t\t-I\n', b'\t\t-I\x7f\n'),
    (b'\t\t-I\n', b'\t\t-I\r\n'),
    (b'\t\t-I\n', b'\t\t-I\n' * 64),
    (b'\t\t-I\n', b'\t\t' + b'a'*4096 + b'\n'),
    (b'\t\t}\n', b'\t}\n'),
    (b'\t\tinner = {', b'\t\tinner = {\n' + b'\t'*9 + b'x = y'),
    (b'\tproperties = keepalive | runatload', b'\tproperties = x\n\tproperties = y'),
    (b'\tproperties = keepalive | runatload', b'\targuments = {\n\t\t/test/python\n\t}'),
    (b'system/com.mastermind.executive.control = {', b'user/com.mastermind.executive.control = {'),
])
def test_launchd_parser_rejects_ambiguous_or_spoofed_service_identity(old, new):
    raw = _launchd_fixture().replace(old, new)
    with pytest.raises(peer.PeerIdentityError):
        installed._parse_launchctl_service(raw, role='control')


@pytest.mark.parametrize('raw', [None, {}, '', b'', b'x'*65537, b'\xff', _launchd_fixture()+b'extra\n', _launchd_fixture()+b'\n', _launchd_fixture()[:-2]])
def test_launchd_parser_closed_input_bounds(raw):
    with pytest.raises(peer.PeerIdentityError):
        installed._parse_launchctl_service(raw, role='control')


@pytest.mark.parametrize('role', [None, {}, [], True, 'CONTROL', 'root', 'gateway '])
def test_launchd_parser_closed_roles(role):
    with pytest.raises(peer.PeerIdentityError):
        installed._parse_launchctl_service(_launchd_fixture(), role=role)


def test_launchd_parse_line_count_and_depth_limits():
    raw = _launchd_fixture().replace(b'\tproperties', b'\n'*1025 + b'\tproperties')
    with pytest.raises(peer.PeerIdentityError):
        installed._parse_launchctl_service(raw, role='control')


def test_launchd_observation_checks_kernel_profile_every_time(monkeypatch):
    calls = []
    def run(argv, *, max_bytes):
        calls.append((argv, max_bytes))
        return b'25.5.0\n' if argv == installed._SYSCTL_OSRELEASE_ARGV else _launchd_fixture()
    monkeypatch.setattr(installed, '_run_bounded', run)
    assert installed._observe_launchd_service('control').pid == 41
    assert installed._observe_launchd_service('control').pid == 41
    assert [c[0] for c in calls] == [installed._SYSCTL_OSRELEASE_ARGV, installed._LAUNCHD_ROLES['control'].launchctl_argv] * 2


@pytest.mark.parametrize('version', [b'25.6.0\n', b'26.0.0\n', b'25.5.0\nextra', b' 25.5.0\n', b'25.5.0\r\n', b'25.5.0\x00'])
def test_launchd_unqualified_kernel_never_reads_service(monkeypatch, version):
    calls = []
    def run(argv, *, max_bytes):
        calls.append(argv)
        return version
    monkeypatch.setattr(installed, '_run_bounded', run)
    with pytest.raises(peer.PeerIdentityError):
        installed._observe_launchd_service('control')
    assert calls == [installed._SYSCTL_OSRELEASE_ARGV]


@pytest.mark.parametrize('value', [b'00000000-0000-0000-0000-000000000000\n', b'garbage', b'01234567-89ab-cdef-0123-456789abcdef\nextra', b' 01234567-89ab-cdef-0123-456789abcdef\n', b'0'*129, None])
def test_boot_observer_refuses_missing_malformed_or_nil_identity(monkeypatch, value):
    monkeypatch.setattr(installed, '_run_bounded', lambda *a, **k: value)
    with pytest.raises(peer.PeerIdentityError):
        installed._observe_real_boot_id()


def test_boot_observer_uses_actual_sysctl_and_normalizes_uppercase(monkeypatch):
    calls = []
    def run(argv, **kw):
        calls.append((argv, kw))
        return b'01234567-89AB-CDEF-0123-456789ABCDEF\n'
    monkeypatch.setattr(installed, '_run_bounded', run)
    assert installed._observe_real_boot_id() == '01234567-89ab-cdef-0123-456789abcdef'
    assert calls == [(installed._SYSCTL_BOOT_ID_ARGV, {'max_bytes':128})]


@pytest.mark.parametrize('argv,limit', [(('/bin/sh','-c','id'), 128), ([],128), (installed._SYSCTL_BOOT_ID_ARGV,True), (installed._SYSCTL_BOOT_ID_ARGV,0), (installed._SYSCTL_BOOT_ID_ARGV,65537)])
def test_bounded_observer_has_no_generic_command_escape(monkeypatch, argv, limit):
    monkeypatch.setattr(installed.subprocess, 'Popen', lambda *a, **k: pytest.fail('must not launch'))
    with pytest.raises(peer.PeerIdentityError):
        installed._run_bounded(argv, max_bytes=limit)


def _observer_test_child(monkeypatch, code):
    # Spawn only an isolated test child. The production fixed command tuple is
    # inspected before substitution; this is no real launchd qualification.
    import subprocess as sp
    import sys as system
    original = sp.Popen
    children = []
    executable = system.executable
    def launch(argv, **kw):
        assert tuple(argv) == installed._SYSCTL_BOOT_ID_ARGV
        assert kw['stdin'] is sp.DEVNULL and kw['stderr'] is sp.DEVNULL
        assert kw['cwd'] == '/' and kw['env'] == installed._LAUNCHD_ENVIRONMENT
        child = original([executable, '-I', '-S', '-B', '-c', code], **kw)
        children.append(child)
        return child
    monkeypatch.setattr(installed.sys, 'platform', 'darwin')
    monkeypatch.setattr(installed.subprocess, 'Popen', launch)
    return children


@pytest.mark.parametrize('code,expected', [
    ('import os;os.write(1,b"ok\\n")', b'ok\n'),
    ('import sys;sys.exit(2)', None),
    ('import os;os.write(1,b"a"*1000000)', None),
    ('import time;time.sleep(5)', None),
])
def test_bounded_observer_reaps_real_owned_test_children(monkeypatch, code, expected):
    children = _observer_test_child(monkeypatch, code)
    monkeypatch.setattr(installed, '_LAUNCHD_TIMEOUT_SECONDS', 0.3)
    if expected is None:
        with pytest.raises(peer.PeerIdentityError):
            installed._run_bounded(installed._SYSCTL_BOOT_ID_ARGV, max_bytes=128)
    else:
        assert installed._run_bounded(installed._SYSCTL_BOOT_ID_ARGV, max_bytes=128) == expected
    assert len(children) == 1 and children[0].poll() is not None
    assert children[0].stdout.closed


def test_child_cleanup_failure_never_returns_positive_observation(monkeypatch):
    children = _observer_test_child(monkeypatch, 'import os;os.write(1,b"ok\\n")')
    real_cleanup = installed._discard_bounded_child
    def report_unproven(child):
        real_cleanup(child)
        return False
    monkeypatch.setattr(installed, '_discard_bounded_child', report_unproven)
    with pytest.raises(peer.PeerIdentityError, match='SERVICE_LAUNCHCTL_CLEANUP_UNPROVEN'):
        installed._run_bounded(installed._SYSCTL_BOOT_ID_ARGV, max_bytes=128)
    assert children[0].poll() is not None
