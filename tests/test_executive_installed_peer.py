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


def test_public_qualify_refuses_forged_capture_and_never_binds(
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
    assert caught.value.code == "PEER_CAPTURE_PROVENANCE_REQUIRED"
    assert bound == []
    assert observed == []
    assert "raw" not in str(caught.value)
    assert EXPECTED not in str(caught.value)


def test_public_surface_has_only_closed_factory_and_one_private_bind_site():
    assert installed.__all__ == ["qualify_installed_peer"]
    source = Path(installed.__file__).read_text(encoding="ascii")
    for banned in (
        "SecCodeCopySelf",
        "SecCodeCreateWithPID",
        "SecCodeCreateWithAuditToken",
        "getpeereid",
    ):
        assert banned not in source
    import ast
    import inspect
    signature = inspect.signature(installed.qualify_installed_peer)
    assert list(signature.parameters) == ["peer", "role"]
    assert signature.parameters["role"].kind is inspect.Parameter.KEYWORD_ONLY
    bindings = [node for node in ast.walk(ast.parse(source))
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_bind_qualified_owner_observation"]
    assert len(bindings) == 1
    assert source.count("_OWNER_CAPABILITY") == 1


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


def test_stdout_close_failure_is_reported_even_when_child_exits(monkeypatch):
    children = _observer_test_child(monkeypatch, 'import os;os.write(1,b"ok\\n")')
    launch_child = installed.subprocess.Popen
    original_streams = []
    class FailingClose:
        def __init__(self, stream):
            self.stream = stream
        def fileno(self):
            return self.stream.fileno()
        def close(self):
            raise OSError('test-only private diagnostic must not escape')
    def launch(*args, **kwargs):
        child = launch_child(*args, **kwargs)
        original_streams.append(child.stdout)
        child.stdout = FailingClose(child.stdout)
        return child
    monkeypatch.setattr(installed.subprocess, 'Popen', launch)
    try:
        with pytest.raises(peer.PeerIdentityError) as failure:
            installed._run_bounded(installed._SYSCTL_BOOT_ID_ARGV, max_bytes=128)
        assert failure.value.code == 'SERVICE_LAUNCHCTL_CLEANUP_UNPROVEN'
        assert children[0].poll() is not None
    finally:
        for stream in original_streams:
            stream.close()
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=1)


"""Independent contract probes; mocked metadata is not host qualification."""
import json
import os
import stat
from types import SimpleNamespace
import pytest
from control_plane import executive_installed_peer as m


def info(gid=0, size=2):
    return SimpleNamespace(st_dev=1, st_ino=2, st_mode=stat.S_IFREG | 0o440,
                           st_uid=0, st_gid=gid, st_nlink=1, st_size=size,
                           st_mtime_ns=1, st_ctime_ns=1)


@pytest.mark.parametrize('gid', [0, 450])
def test_bounded_reader_accepts_exact_expected_group(monkeypatch, gid):
    observed = info(gid)
    blocks = iter([b'{}', b''])
    closed = []
    fake = SimpleNamespace(lstat=lambda p: observed, fstat=lambda fd: observed,
                           open=lambda *a: 19, read=lambda *a: next(blocks),
                           close=lambda fd: closed.append(fd),
                           O_RDONLY=os.O_RDONLY, O_NOFOLLOW=os.O_NOFOLLOW,
                           O_CLOEXEC=os.O_CLOEXEC, O_NONBLOCK=os.O_NONBLOCK)
    monkeypatch.setattr(m, 'os', fake)
    monkeypatch.setattr(m, 'has_macos_acl', lambda *a, **k: False)
    data, _ = m._read_trusted_bytes('/fixed/config', budget=m._Budget(25),
                                   maximum=100, expected_mode=0o440,
                                   expected_gid=gid)
    assert data == b'{}' and closed == [19]


def test_control_projection_accepts_real_sha1_release_identity(monkeypatch):
    document = {'proof_base_sha': 'a' * 40, 'control_uid': 450,
                'python_runtime_provenance_digest': 'b' * 64}
    raw = json.dumps(document).encode()
    monkeypatch.setattr(m, "_observe_ancestors", lambda *a: ())
    monkeypatch.setattr(m, '_read_trusted_bytes',
                        lambda *a, **kw: (raw, info(450, len(raw))))
    result = m._verify_control_projection(m._Budget(25))
    assert result.release == 'a' * 40
    assert result.provenance_digest == 'b' * 64


def test_no_binding_can_be_issued_after_overall_deadline(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(m, 'time', SimpleNamespace(monotonic=lambda: now[0]))
    capture = m._peer_identity._CaptureState(lambda: None, None, object(), os.getpid())
    monkeypatch.setattr(m._peer_identity, '_current_capture', lambda peer: capture)
    def slow_qualification(*args):
        now[0] = 26.0
        return object()
    monkeypatch.setattr(m, '_qualify', slow_qualification)
    calls = []
    def bind(*args):
        calls.append(True)
        return object.__new__(m._peer_identity.InstalledServicePeerBinding)
    monkeypatch.setattr(m, '_owner_binding', bind)
    with pytest.raises(m.PeerIdentityError, match='BUDGET'):
        m.qualify_installed_peer(object(), role='control')
    assert calls == []

QUALIFIED_CONTROL_PLIST = json.loads(r'''
{
  "AbandonProcessGroup": false,
  "EnvironmentVariables": {
    "HOME": "/var/db/mastermind-executive/control/home",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "NO_COLOR": "1",
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    "PYTHONUNBUFFERED": "1",
    "TZ": "UTC"
  },
  "ExitTimeOut": 15,
  "GroupName": "_mastermind_exec",
  "HardResourceLimits": {
    "Core": 0,
    "FileSize": 67108864
  },
  "KeepAlive": true,
  "Label": "com.mastermind.executive.control",
  "ProcessType": "Interactive",
  "ProgramArguments": [
    "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12",
    "-I",
    "-S",
    "-B",
    "/Library/Application Support/MastermindExecutive/releases/f91847688f8126511c854ab253cd5c3cb67baa4e/scripts/executive_os_phase1c_control_wrapper.py",
    "--config",
    "/Library/Application Support/MastermindExecutive/config/control.json",
    "--sentinel-file",
    "/Library/Application Support/MastermindExecutive/config/control-env-canary",
    "--attestation",
    "/var/db/mastermind-executive/control/canaries/control-environment-attestation.json",
    "--release-root",
    "/Library/Application Support/MastermindExecutive/releases/f91847688f8126511c854ab253cd5c3cb67baa4e"
  ],
  "RunAtLoad": true,
  "Sockets": {
    "CeoIngress": {
      "SockPassive": true,
      "SockPathGroup": 452,
      "SockPathMode": 432,
      "SockPathName": "/var/run/mastermind-executive/ceo-ingress.sock",
      "SockPathOwner": 450,
      "SockType": "stream"
    },
    "DialogueObservation": {
      "SockPassive": true,
      "SockPathGroup": 457,
      "SockPathMode": 432,
      "SockPathName": "/var/run/mastermind-dialogue-observation/dialogue-observation.sock",
      "SockPathOwner": 450,
      "SockType": "stream"
    },
    "Operator": {
      "SockPassive": true,
      "SockPathGroup": 453,
      "SockPathMode": 432,
      "SockPathName": "/var/run/mastermind-executive/control.sock",
      "SockPathOwner": 450,
      "SockType": "stream"
    }
  },
  "StandardErrorPath": "/var/log/mastermind-executive/control/stderr.log",
  "StandardOutPath": "/var/log/mastermind-executive/control/stdout.log",
  "ThrottleInterval": 10,
  "Umask": 63,
  "UserName": "_mastermind_exec",
  "WorkingDirectory": "/Library/Application Support/MastermindExecutive/releases/f91847688f8126511c854ab253cd5c3cb67baa4e"
}
''')

QUALIFIED_GATEWAY_PLIST = json.loads(r'''
{
  "EnvironmentVariables": {
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONNOUSERSITE": "1"
  },
  "GroupName": "_mastermind_executive_mcp",
  "KeepAlive": true,
  "Label": "com.mastermind.executive.mcp",
  "ProcessType": "Background",
  "ProgramArguments": [
    "/Library/Application Support/MastermindExecutive/network-runtimes/9512f58e382dbb94c730f74a0d80935e460f6c2707da7689b4beaecead9cb94d/bin/python",
    "-I",
    "-B",
    "/Library/Application Support/MastermindExecutive/releases/3c35c5f8c4609c5bbaa4db424521facb6ad3757d/ops/executive_os/executive_mcp_entry.py",
    "--config",
    "/Library/Application Support/MastermindExecutive/config/executive-mcp.json"
  ],
  "RunAtLoad": true,
  "StandardErrorPath": "/var/log/mastermind-executive/mcp-auth/service.stderr.log",
  "StandardOutPath": "/var/log/mastermind-executive/mcp-auth/service.stdout.log",
  "ThrottleInterval": 10,
  "Umask": 63,
  "UserName": "_mastermind_executive_mcp",
  "WorkingDirectory": "/Library/Application Support/MastermindExecutive/releases/3c35c5f8c4609c5bbaa4db424521facb6ad3757d"
}
''')


import copy
import dataclasses
import plistlib
import socket


@pytest.mark.parametrize('role,profile', [('control', QUALIFIED_CONTROL_PLIST), ('gateway', QUALIFIED_GATEWAY_PLIST)])
def test_complete_observed_plist_profile_is_accepted(role, profile):
    parsed = m._load_strict_plist(plistlib.dumps(profile), code='PLIST_INVALID')
    releases = []
    assert m._profile_matches(m._EXPECTED_PLIST_PROFILES[role], parsed, releases)
    assert releases == [profile['WorkingDirectory'].rsplit('/', 1)[1]]


@pytest.mark.parametrize('role,profile', [('control', QUALIFIED_CONTROL_PLIST), ('gateway', QUALIFIED_GATEWAY_PLIST)])
@pytest.mark.parametrize('change', ['extra', 'missing', 'program', 'environment', 'arguments', 'uid', 'workdir', 'bool_int'])
def test_plist_profile_drift_refuses(role, profile, change):
    value = copy.deepcopy(profile)
    if change == 'extra': value['UnqualifiedKey'] = True
    elif change == 'missing': del value['Umask']
    elif change == 'program': value['Program'] = '/other/python'
    elif change == 'environment': value['EnvironmentVariables']['PYTHONPATH'] = '/writable'
    elif change == 'arguments': value['ProgramArguments'].append('--unqualified')
    elif change == 'uid': value['UserName'] = 'root'
    elif change == 'workdir': value['WorkingDirectory'] = '/tmp/release'
    else: value['RunAtLoad'] = 1
    assert not m._profile_matches(m._EXPECTED_PLIST_PROFILES[role], value, [])


@pytest.mark.parametrize('raw', [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'[]',
                                b'{"a":1e999}', b'{"a":-1e999}', b'{"a":{"nested":[1e999]}}'])
def test_strict_json_refuses_ambiguous_or_nonfinite_document(raw):
    with pytest.raises(peer.PeerIdentityError): m._load_strict_json(raw, code='BAD_JSON')


def test_strict_json_preserves_finite_numbers_and_integers():
    assert m._load_strict_json(b'{"a":[1.25,-2e3,3e-4,42,1e308]}', code='BAD_JSON') == {
        'a': [1.25, -2000.0, 0.0003, 42, 1e308]
    }


def _installed_config_read(monkeypatch, document):
    raw = json.dumps(document, sort_keys=True, separators=(',', ':')).encode()
    identity = SimpleNamespace(
        st_dev=1, st_ino=2, st_mode=stat.S_IFREG | 0o644,
        st_uid=0, st_gid=0, st_nlink=1, st_size=len(raw),
        st_mtime_ns=3, st_ctime_ns=4,
    )
    monkeypatch.setattr(m, '_observe_ancestors', lambda *a: ())
    monkeypatch.setattr(m, '_read_trusted_bytes', lambda *a, **k: (raw, identity))


def _gateway_install_document(release, profile='release_control_v1'):
    return {
        'schema': 'mastermind.executive_mcp_install.v1',
        'release_sha': release,
        'service_uid': 458,
        'ceo_ingress_socket_path': '/var/run/mastermind-executive/ceo-ingress.sock',
        'port': 8443,
        'policies': {},
        'audit_root': '/var/log/mastermind-executive/mcp-auth',
        'executive_mcp_profile': profile,
    }


def test_gateway_role_config_accepts_exact_release_control_profile(monkeypatch):
    from ops.executive_os.executive_mcp_entry import CONFIG_SCHEMA

    release = 'a' * 40
    _installed_config_read(monkeypatch, _gateway_install_document(release))
    observed = m._verify_role_config(m._role_topology('gateway'), release, m._Budget(25))

    assert m._GATEWAY_CONFIG_SCHEMA == CONFIG_SCHEMA
    profile_source = (
        Path(__file__).parents[1] / 'integrations/executive_mcp/release_control.py'
    ).read_text()
    assert 'RELEASE_CONTROL_PROFILE = "release_control_v1"' in profile_source
    assert m._GATEWAY_MCP_PROFILE == 'release_control_v1'
    assert observed.release == release


def test_gateway_role_config_accepts_exact_combined_release_profile(monkeypatch):
    from integrations.executive_mcp.web_ceo_release import WEB_CEO_RELEASE_PROFILE

    release = 'a' * 40
    document = _gateway_install_document(release, WEB_CEO_RELEASE_PROFILE)
    _installed_config_read(monkeypatch, document)
    observed = m._verify_role_config(m._role_topology('gateway'), release, m._Budget(25))
    assert m._GATEWAY_MCP_PROFILES == ('release_control_v1', WEB_CEO_RELEASE_PROFILE)
    assert observed.release == release
    assert observed.digest == m.hashlib.sha256(json.dumps(document, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


@pytest.mark.parametrize('profile', [
    'web_ceo_release_v2', 'web_ceo_release_v1 ', 'WEB_CEO_RELEASE_V1',
    'web_ceo_v3', 'personal_read', '',
])
def test_gateway_role_config_refuses_combined_profile_aliases(monkeypatch, profile):
    release = 'a' * 40
    _installed_config_read(monkeypatch, _gateway_install_document(release, profile))
    with pytest.raises(peer.PeerIdentityError):
        m._verify_role_config(m._role_topology('gateway'), release, m._Budget(25))


@pytest.mark.parametrize('profile,code', [
    ('web_ceo_v2', 'SERVICE_CONFIG_PROFILE_DRIFT'),
    ('legacy', 'SERVICE_CONFIG_PROFILE_DRIFT'),
    ('release_control_v2', 'SERVICE_CONFIG_PROFILE_DRIFT'),
    (None, 'SERVICE_CONFIG_SCHEMA_DRIFT'),
    (458, 'SERVICE_CONFIG_SCHEMA_DRIFT'),
])
def test_gateway_role_config_refuses_other_profiles(monkeypatch, profile, code):
    release = 'a' * 40
    _installed_config_read(monkeypatch, _gateway_install_document(release, profile))
    with pytest.raises(peer.PeerIdentityError, match=code):
        m._verify_role_config(m._role_topology('gateway'), release, m._Budget(25))


def test_gateway_role_config_requires_profile_field(monkeypatch):
    release = 'a' * 40
    document = _gateway_install_document(release)
    del document['executive_mcp_profile']
    _installed_config_read(monkeypatch, document)
    with pytest.raises(peer.PeerIdentityError, match='SERVICE_CONFIG_SCHEMA_DRIFT'):
        m._verify_role_config(m._role_topology('gateway'), release, m._Budget(25))


def test_gateway_role_config_requires_current_schema_field(monkeypatch):
    release = 'a' * 40
    document = _gateway_install_document(release)
    document['schema_version'] = document.pop('schema')
    _installed_config_read(monkeypatch, document)
    with pytest.raises(peer.PeerIdentityError, match='SERVICE_CONFIG_SCHEMA_DRIFT'):
        m._verify_role_config(m._role_topology('gateway'), release, m._Budget(25))


def test_control_role_config_is_unchanged(monkeypatch):
    release = 'a' * 40
    _installed_config_read(monkeypatch, {
        'proof_base_sha': release,
        'control_uid': 450,
        'python_runtime_provenance_digest': 'b' * 64,
    })
    observed = m._verify_role_config(m._role_topology('control'), release, m._Budget(25))
    assert observed.release == release
    assert observed.provenance_digest == ''


@pytest.mark.parametrize('changed_field', [None, 'st_ino', 'st_mtime_ns', 'st_ctime_ns'])
def test_release_recheck_retains_manifest_descriptor_identity(monkeypatch, changed_field):
    """An unchanged content digest must not hide replacement or metadata drift."""
    raw = b'{"manifest":"unchanged"}'
    original = SimpleNamespace(st_dev=1, st_ino=12, st_mode=0o100444,
                               st_uid=0, st_gid=0, st_nlink=1, st_size=len(raw),
                               st_mtime_ns=20, st_ctime_ns=30)
    reread = copy.copy(original)
    if changed_field:
        setattr(reread, changed_field, getattr(reread, changed_field) + 1)
    digest = m.hashlib.sha256(raw).hexdigest()
    before = m._TreeObservation(
        release='a' * 40, wrapper_relative='wrapper.py', manifest_digest=digest,
        wrapper_digest=digest, identities=(), digests=(),
        root_identity=m._object_identity(original), ancestor_identities=(),
        manifest_identity=m._object_identity(original),
    )
    monkeypatch.setattr(m, '_open_trusted', lambda *a, **k: (999, original, original))
    monkeypatch.setattr(m, '_close', lambda *a: None)
    monkeypatch.setattr(m, '_observe_ancestors', lambda *a: ())
    monkeypatch.setattr(m, '_read_trusted_bytes', lambda *a, **k: (raw, reread))
    monkeypatch.setattr(m, '_walk_release', lambda *a, **k: [])
    if changed_field:
        with pytest.raises(peer.PeerIdentityError, match='SERVICE_MANIFEST_CHANGED'):
            m._recheck_release(before, m._Budget(25))
    else:
        m._recheck_release(before, m._Budget(25))


def test_plist_duplicate_key_refuses_before_dict_collapse():
    raw = b'<?xml version="1.0"?><plist><dict><key>x</key><true/><key>x</key><false/></dict></plist>'
    with pytest.raises(peer.PeerIdentityError): m._load_strict_plist(raw, code='BAD_PLIST')


@pytest.mark.parametrize('role', [None, True, [], {}, 'worker', 'control\n'])
def test_factory_role_is_closed_even_for_unhashable_values(role):
    with pytest.raises(peer.PeerIdentityError): m.qualify_installed_peer(object(), role=role)


@pytest.fixture
def composition(monkeypatch):
    """Real A2 binding composition with mocked host observations, never host proof."""
    opened = []
    def make(role):
        first, second = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        opened.extend([first, second])
        topology = m._role_topology(role)
        kernel = peer._KernelObservation(b'Z' * 32, topology.service_uid, 1234, 9876, peer._descriptor_identity(first))
        monkeypatch.setattr(peer, '_observe_socket', lambda _: kernel)
        capture = peer.capture_peer_identity(first)
        profile = QUALIFIED_CONTROL_PLIST if role == 'control' else QUALIFIED_GATEWAY_PLIST
        release = profile['WorkingDirectory'].rsplit('/', 1)[1]
        plist = m._PlistObservation(release, 'b' * 64, tuple(profile['ProgramArguments']), (), ())
        config = m._ConfigObservation('c' * 64, 'd' * 64, release, (), ())
        projection = m._ConfigObservation('e' * 64, 'f' * 64, release, (), ())
        launch = m._LaunchdObservation(topology.label if hasattr(topology, 'label') else m._LAUNCHD_ROLES[role].label,
            m._LAUNCHD_ROLES[role].plist_path, 'running', topology.launcher, plist.argv,
            profile['WorkingDirectory'], topology.username, topology.group, capture.pid)
        dynamic = m._DynamicCodeObservation('1' * 64, '2' * 64, 0, m._PYTHON_MAIN_EXECUTABLE)
        tree = m._TreeObservation(release, topology.wrapper_relative, '3' * 64, '4' * 64, (), (), (), (), ())
        monkeypatch.setattr(m, '_observe_real_boot_id', lambda: '11111111-1111-4111-8111-111111111111')
        monkeypatch.setattr(m, '_observe_launchd_service', lambda _: launch)
        monkeypatch.setattr(m, '_verify_role_plist', lambda *a, **k: plist)
        monkeypatch.setattr(m, '_verify_role_config', lambda *a, **k: config)
        monkeypatch.setattr(m, '_verify_control_projection', lambda *a: projection)
        monkeypatch.setattr(m, '_verify_release', lambda *a: tree)
        monkeypatch.setattr(m, '_verify_python_runtime', lambda *a: object())
        monkeypatch.setattr(m, '_verify_network_closure', lambda *a: object())
        monkeypatch.setattr(m, '_observe_dynamic_code', lambda *a: dynamic)
        for name in ('_recheck_release', '_recheck_python_runtime', '_recheck_network_closure'):
            monkeypatch.setattr(m, name, lambda *a: None)
        return SimpleNamespace(role=role, peer=capture, connection=first, launch=launch,
                               plist=plist, config=config, projection=projection, dynamic=dynamic)
    yield make
    for connection in opened: connection.close()


@pytest.mark.parametrize('role', ['control', 'gateway'])
def test_complete_composition_binds_only_original_capture(composition, role):
    value = composition(role)
    binding = m.qualify_installed_peer(value.peer, role=role)
    context = peer.require_installed_service_peer(value.peer, binding)
    assert context.service_label == value.launch.service_label
    assert context.installed_release == value.plist.release
    assert context.config_digest == value.config.digest
    assert context.connection_instance is value.peer.connection_instance
    recaptured = peer.capture_peer_identity(value.connection)
    with pytest.raises(peer.PeerIdentityError): peer.require_installed_service_peer(recaptured, binding)


@pytest.mark.parametrize('role', ['control', 'gateway'])
@pytest.mark.parametrize('failure', ['pid', 'username', 'group', 'program', 'argv', 'cwd', 'dynamic_path', 'dynamic_status'])
def test_composition_refuses_identity_mismatch(monkeypatch, composition, role, failure):
    value = composition(role)
    if failure.startswith('dynamic_'):
        update = {'executable_path': '/other/python'} if failure == 'dynamic_path' else {'dynamic_code_status': 1}
        bad = dataclasses.replace(value.dynamic, **update)
        monkeypatch.setattr(m, '_observe_dynamic_code', lambda *a: bad)
    else:
        change = {'pid': {'pid': value.peer.pid + 1}, 'username': {'username': 'root'},
                  'group': {'group': 'wheel'}, 'program': {'program': '/other/python'},
                  'argv': {'argv': value.launch.argv + ('--other',)},
                  'cwd': {'working_directory': '/other/release'}}[failure]
        bad = dataclasses.replace(value.launch, **change)
        monkeypatch.setattr(m, '_observe_launchd_service', lambda *a: bad)
    with pytest.raises(peer.PeerIdentityError): m.qualify_installed_peer(value.peer, role=role)


@pytest.mark.parametrize('seam', ['_observe_real_boot_id', '_observe_launchd_service', '_observe_dynamic_code', '_verify_role_config', '_verify_role_plist', '_verify_control_projection'])
def test_composition_refuses_changed_observation_on_recheck(monkeypatch, composition, seam):
    value = composition('gateway')
    original = getattr(m, seam)
    calls = []
    def changed(*args, **kwargs):
        calls.append(True)
        result = original(*args, **kwargs)
        return result if len(calls) == 1 else object()
    monkeypatch.setattr(m, seam, changed)
    with pytest.raises(peer.PeerIdentityError): m.qualify_installed_peer(value.peer, role='gateway')


@pytest.mark.parametrize('seam', ['_verify_release', '_verify_python_runtime', '_verify_network_closure', '_verify_control_projection', '_recheck_release', '_recheck_python_runtime', '_recheck_network_closure'])
def test_failed_closure_or_projection_never_issues_binding(monkeypatch, composition, seam):
    value = composition('gateway')
    def unavailable(*args): raise peer.PeerIdentityError('CLOSED_INPUT_UNAVAILABLE')
    monkeypatch.setattr(m, seam, unavailable)
    with pytest.raises(peer.PeerIdentityError, match='CLOSED_INPUT_UNAVAILABLE'):
        m.qualify_installed_peer(value.peer, role='gateway')


@pytest.mark.parametrize('fault', ['writable', 'acl', 'scandir'])
def test_python_inventory_reaches_deep_import_object(monkeypatch, tmp_path, fault):
    base = tmp_path / 'python'; nested = base / 'lib' / 'python3.12' / 'deep'
    nested.mkdir(parents=True)
    leaf = nested / 'module.py'; leaf.write_bytes(b'pass\n')
    for directory in (base, base/'lib', base/'lib/python3.12', nested): directory.chmod(0o755)
    leaf.chmod(0o666 if fault == 'writable' else 0o644)
    real_os = os
    fake_os = SimpleNamespace(**vars(real_os))
    def root_info(value):
        return SimpleNamespace(**{key: getattr(value, key) for key in
            ('st_dev','st_ino','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')}, st_uid=0, st_gid=0)
    fake_os.lstat = lambda path: root_info(real_os.lstat(path))
    fake_os.fstat = lambda fd: root_info(real_os.fstat(fd))
    if fault == 'scandir':
        def denied(path):
            if str(path) == str(nested): raise PermissionError('injected scan failure')
            return real_os.scandir(path)
        fake_os.scandir = denied
    monkeypatch.setattr(m, 'os', fake_os)
    monkeypatch.setattr(m, '_PYTHON_BASE', str(base))
    monkeypatch.setattr(m, '_PYTHON_LINK_INDEX', {})
    monkeypatch.setattr(m, 'has_macos_acl', lambda path, **kw: fault == 'acl' and str(path) == str(leaf))
    with pytest.raises(peer.PeerIdentityError): m._inventory_python_base(m._Budget(25))


def test_directory_scan_enforces_deadline_after_iterator_close(monkeypatch):
    now = [0.0]
    class Scan:
        def __enter__(self): return iter([])
        def __exit__(self, *a): now[0] = 26.0
    monkeypatch.setattr(m, 'time', SimpleNamespace(monotonic=lambda: now[0]))
    monkeypatch.setattr(m, 'os', SimpleNamespace(scandir=lambda path: Scan()))
    with pytest.raises(peer.PeerIdentityError, match='BUDGET'):
        m._directory_entries('/fixed', m._Budget(25))


def test_plist_entity_declaration_refused():
    raw = b'<?xml version="1.0"?><!DOCTYPE plist [<!ENTITY x "expanded">]><plist><dict><key>x</key><string>&x;</string></dict></plist>'
    with pytest.raises(peer.PeerIdentityError): m._load_strict_plist(raw, code='BAD_PLIST')


@pytest.mark.parametrize('argv,allow_empty,merge_stderr', [
    (('/bin/sh', '-c', 'true'), True, False),
    (m._CODESIGN_METADATA_ARGV, True, True),
    (m._CODESIGN_VERIFY_ARGV, True, True),
    (m._CODESIGN_VERIFY_ARGV, False, False),
])
def test_extra_subprocess_interface_refuses_unqualified_combinations(monkeypatch, argv, allow_empty, merge_stderr):
    def forbidden(*a, **kw): raise AssertionError('must refuse before a child')
    monkeypatch.setattr(m.subprocess, 'Popen', forbidden)
    with pytest.raises(peer.PeerIdentityError, match='COMMAND_NOT_ALLOWED'):
        m._run_bounded_readonly(argv, budget=m._Budget(25), max_bytes=4096,
                               allow_empty=allow_empty, merge_stderr=merge_stderr)


class _FakeProcPidInfo:
    """Mock the libproc ABI, never query a real process."""

    def __init__(self):
        self.argtypes = None
        self.restype = None
        self.calls = []
        self.size = 56
        self.unique_id = 113769795
        self.pidversion = 235172879
        self.error = None

    def __call__(self, pid, flavor, argument, output, size):
        self.calls.append((pid, flavor, argument, size, ctypes.get_errno()))
        if self.error is not None:
            raise self.error
        result = ctypes.cast(output, ctypes.POINTER(installed._ProcUniqueIdentifierInfo)).contents
        result.p_uniqueid = self.unique_id
        result.p_idversion = self.pidversion
        return self.size


@pytest.fixture
def process_instance_api(monkeypatch):
    query = _FakeProcPidInfo()
    loads = []

    class Library:
        proc_pidinfo = query

    def load(path, **kwargs):
        loads.append((path, kwargs))
        return Library()

    monkeypatch.setattr(installed.sys, "platform", "darwin")
    monkeypatch.setattr(installed.ctypes, "CDLL", load)
    return query, loads


def test_process_instance_abi_is_exact_56_byte_native_layout():
    layout = installed._ProcUniqueIdentifierInfo
    assert ctypes.sizeof(layout) == 56
    assert [(name, getattr(layout, name).offset) for name, _ in layout._fields_] == [
        ("p_uuid", 0), ("p_uniqueid", 16), ("p_puniqueid", 24),
        ("p_idversion", 32), ("p_orig_ppidversion", 36),
        ("p_reserve2", 40), ("p_reserve3", 48),
    ]


@pytest.mark.parametrize("pid", [1, 17778, (1 << 31) - 1])
def test_process_instance_binds_exact_native_signature_and_clears_errno(process_instance_api, pid):
    query, loads = process_instance_api
    ctypes.set_errno(123)
    value = installed._observe_process_instance(pid)
    assert query.calls == [(pid, 17, 0, 56, 0)]
    assert loads == [("/usr/lib/libproc.dylib", {"use_errno": True})]
    assert query.argtypes == [ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                              ctypes.c_void_p, ctypes.c_int]
    assert query.restype is ctypes.c_int
    assert (value.unique_id, value.pidversion) == (query.unique_id, query.pidversion)
    assert list(value.__dataclass_fields__) == ["unique_id", "pidversion"]
    with pytest.raises(AttributeError):
        value.unique_id = 1
    assert "_observe_process_instance" not in installed.__all__


def test_process_instance_reads_fresh_identity_and_distinguishes_exec(process_instance_api):
    query, _ = process_instance_api
    first = installed._observe_process_instance(123)
    assert installed._observe_process_instance(123) == first
    query.pidversion += 1
    second = installed._observe_process_instance(123)
    assert second.unique_id == first.unique_id
    assert second != first
    query.unique_id += 1
    assert installed._observe_process_instance(123) != second
    assert len(query.calls) == 4


@pytest.mark.parametrize("pid", [True, False, None, "123", 1.0, b"1", [], {}, 0, -1, 1 << 31, 1 << 70])
def test_process_instance_invalid_pid_never_loads_native_api(process_instance_api, pid):
    query, loads = process_instance_api
    with pytest.raises(peer.PeerIdentityError, match="^SERVICE_PROCESS_PID_INVALID$"):
        installed._observe_process_instance(pid)
    assert query.calls == []
    assert loads == []


def test_process_instance_refuses_int_subclass_before_native_api(process_instance_api):
    class Pid(int):
        pass
    query, loads = process_instance_api
    with pytest.raises(peer.PeerIdentityError, match="^SERVICE_PROCESS_PID_INVALID$"):
        installed._observe_process_instance(Pid(123))
    assert query.calls == loads == []


def test_process_instance_non_darwin_never_loads_api(monkeypatch, process_instance_api):
    query, loads = process_instance_api
    monkeypatch.setattr(installed.sys, "platform", "linux")
    with pytest.raises(peer.PeerIdentityError, match="^PEER_PLATFORM_UNSUPPORTED$"):
        installed._observe_process_instance(123)
    assert query.calls == loads == []


def test_process_instance_wrong_layout_never_loads_api(monkeypatch, process_instance_api):
    query, loads = process_instance_api
    real_sizeof = ctypes.sizeof
    monkeypatch.setattr(installed.ctypes, "sizeof", lambda kind:
                        55 if kind is installed._ProcUniqueIdentifierInfo else real_sizeof(kind))
    with pytest.raises(peer.PeerIdentityError, match="^SERVICE_PROCESS_ABI_UNSUPPORTED$"):
        installed._observe_process_instance(123)
    assert query.calls == loads == []


@pytest.mark.parametrize("failure", ["library", "symbol", "call"])
def test_process_instance_api_failure_is_short_and_nonsecret(monkeypatch, process_instance_api, failure):
    query, _ = process_instance_api
    if failure == "library":
        def unavailable(*args, **kwargs):
            raise OSError("private path /secret and PID 123")
        monkeypatch.setattr(installed.ctypes, "CDLL", unavailable)
    elif failure == "symbol":
        monkeypatch.setattr(installed.ctypes, "CDLL", lambda *args, **kwargs: object())
    else:
        query.error = OSError("private path /secret and PID 123")
    with pytest.raises(peer.PeerIdentityError) as caught:
        installed._observe_process_instance(123)
    assert str(caught.value) == "SERVICE_PROCESS_OBSERVATION_UNAVAILABLE"
    assert caught.value.__suppress_context__ is True


@pytest.mark.parametrize("size", [-1, 0, 1, 55, 57, 112, True, 56.0, None])
def test_process_instance_nonexact_return_never_yields_identity(process_instance_api, size):
    query, _ = process_instance_api
    query.size = size
    with pytest.raises(peer.PeerIdentityError, match="^SERVICE_PROCESS_OBSERVATION_SIZE_INVALID$"):
        installed._observe_process_instance(123)


@pytest.mark.parametrize("unique_id,pidversion", [(0, 1), (1, 0), (1, -1), (1, -(1 << 31)), (0, 0)])
def test_process_instance_nonpositive_identity_refuses(process_instance_api, unique_id, pidversion):
    query, _ = process_instance_api
    query.unique_id, query.pidversion = unique_id, pidversion
    with pytest.raises(peer.PeerIdentityError, match="^SERVICE_PROCESS_IDENTITY_INVALID$"):
        installed._observe_process_instance(123)


# Private request deadline support. No host qualification is performed.
import inspect

class IntSubclass(int):
    pass


def clock(monkeypatch, start=1_000_000_000):
    now = [start]
    sleeps = []
    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += round(seconds * 1_000_000_000)
    monkeypatch.setattr(m, "time", SimpleNamespace(
        monotonic=lambda: now[0] / 1_000_000_000,
        monotonic_ns=lambda: now[0], sleep=sleep))
    return now, sleeps


@pytest.mark.parametrize("endpoint", [True, False, 0, -1, 1.5, "2", [], {}, IntSubclass(2)])
def test_invalid_endpoint_has_no_clock_or_observation(monkeypatch, endpoint):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid endpoint reached clock or observation")
    monkeypatch.setattr(m, "time", SimpleNamespace(monotonic=forbidden, monotonic_ns=forbidden))
    monkeypatch.setattr(m._peer_identity, "_current_capture", forbidden)
    with pytest.raises((ValueError, m.PeerIdentityError)):
        m._Budget(25, deadline_monotonic_ns=endpoint)
    with pytest.raises((ValueError, m.PeerIdentityError)):
        m._qualify_installed_peer_with_deadline(object(), role="control", deadline_monotonic_ns=endpoint)


def test_public_signature_unchanged():
    assert str(inspect.signature(m.qualify_installed_peer)) == "(peer, *, role)"


@pytest.mark.parametrize("explicit_none", [False, True])
def test_legacy_budget_never_reads_nanosecond_clock(monkeypatch, explicit_none):
    now = [0.0]
    monkeypatch.setattr(m, "time", SimpleNamespace(
        monotonic=lambda: now[0],
        monotonic_ns=lambda: pytest.fail("legacy budget read new clock")))
    budget = m._Budget(25, **({"deadline_monotonic_ns": None} if explicit_none else {}))
    assert budget.check() == 25
    now[0] = 24.5
    assert budget.check() == .5
    now[0] = 25
    with pytest.raises(m.PeerIdentityError):
        budget.check()


@pytest.mark.parametrize("endpoint,expected", [(3_000_000_000, 2), (100_000_000_000, 25), (10**1000, 25)])
def test_parent_and_local_cap_min_compose(monkeypatch, endpoint, expected):
    now, _ = clock(monkeypatch)
    budget = m._Budget(25, deadline_monotonic_ns=endpoint)
    assert budget.check() == expected
    now[0] += 1_000_000_000
    assert budget.check() == expected - 1


def test_one_endpoint_is_never_replenished(monkeypatch):
    now, _ = clock(monkeypatch)
    budget = m._Budget(25, deadline_monotonic_ns=4_000_000_000)
    for remaining in [3, 2, 1]:
        assert budget.check() == remaining
        now[0] += 1_000_000_000
    with pytest.raises(m.PeerIdentityError):
        budget.check()


@pytest.mark.parametrize("offset", [0, -1])
def test_expired_private_qualification_has_zero_capture(monkeypatch, offset):
    now, _ = clock(monkeypatch)
    monkeypatch.setattr(m._peer_identity, "_current_capture", lambda *a: pytest.fail("expired capture"))
    with pytest.raises(m.PeerIdentityError):
        m._qualify_installed_peer_with_deadline(object(), role="control", deadline_monotonic_ns=now[0] + offset)


def qualification_seams(monkeypatch):
    import os
    capture = m._peer_identity._CaptureState(lambda: None, None, object(), os.getpid())
    monkeypatch.setattr(m._peer_identity, "_current_capture", lambda peer: capture)
    return object.__new__(m._peer_identity.InstalledServicePeerBinding)


def test_late_qualification_never_calls_binding(monkeypatch):
    now, _ = clock(monkeypatch)
    qualification_seams(monkeypatch)
    def qualify(*args):
        now[0] = 2_000_000_000
        return object()
    monkeypatch.setattr(m, "_qualify", qualify)
    monkeypatch.setattr(m, "_owner_binding", lambda *a: pytest.fail("late binding"))
    with pytest.raises(m.PeerIdentityError):
        m._qualify_installed_peer_with_deadline(object(), role="control", deadline_monotonic_ns=2_000_000_000)


def test_original_qualification_refusal_survives_expiry(monkeypatch):
    now, _ = clock(monkeypatch)
    qualification_seams(monkeypatch)
    original = m.PeerIdentityError("SERVICE_PEER_IDENTITY_MISMATCH")
    def qualify(*args):
        now[0] = 2_000_000_000
        raise original
    monkeypatch.setattr(m, "_qualify", qualify)
    with pytest.raises(m.PeerIdentityError) as failure:
        m._qualify_installed_peer_with_deadline(object(), role="control", deadline_monotonic_ns=2_000_000_000)
    assert failure.value is original


def test_binding_returning_at_deadline_is_not_exposed(monkeypatch):
    now, _ = clock(monkeypatch)
    binding = qualification_seams(monkeypatch)
    monkeypatch.setattr(m, "_qualify", lambda *a: object())
    def bind(*args):
        now[0] = 2_000_000_000
        return binding
    monkeypatch.setattr(m, "_owner_binding", bind)
    with pytest.raises(m.PeerIdentityError):
        m._qualify_installed_peer_with_deadline(object(), role="control", deadline_monotonic_ns=2_000_000_000)


def child_harness(monkeypatch, *, late_stage=None, failure_stage=None, cleanup_ok=True):
    now, sleeps = clock(monkeypatch)
    endpoint = 2_000_000_000
    calls = []
    blocks = iter([b"ok\n", b""])
    def step(name):
        calls.append(name)
        if name == late_stage or name == failure_stage:
            now[0] = endpoint
        if name == failure_stage:
            raise OSError("private test diagnostic")
    class Stream:
        def fileno(self):
            step("fileno")
            return 123
        def close(self):
            step("close")
    class Child:
        stdout = Stream()
        def poll(self):
            step("poll")
            return 0
        def kill(self):
            step("kill")
        def wait(self, *, timeout):
            step("wait")
            return 0
    child = Child()
    def launch(*args, **kwargs):
        step("spawn")
        return child
    def discard(process):
        assert process is child
        step("cleanup")
        return cleanup_ok
    class Selector:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            step("selector_close")
        def register(self, *args):
            step("register")
        def select(self, timeout):
            assert 0 < timeout <= (endpoint - now[0]) / 1_000_000_000
            step("select")
            return [object()]
    def read(*args):
        step("read")
        return next(blocks)
    monkeypatch.setattr(m, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(m, "subprocess", SimpleNamespace(Popen=launch, DEVNULL=-3, PIPE=-1))
    monkeypatch.setattr(m, "selectors", SimpleNamespace(DefaultSelector=Selector, EVENT_READ=1))
    monkeypatch.setattr(m, "os", SimpleNamespace(set_blocking=lambda *a: step("nonblock"), read=read))
    monkeypatch.setattr(m, "_discard_bounded_child", discard)
    return now, calls, endpoint


@pytest.mark.parametrize("stage", ["spawn", "fileno", "nonblock", "register", "select", "read", "selector_close", "poll", "cleanup"])
def test_late_child_phase_refuses_with_one_cleanup(monkeypatch, stage):
    now, calls, endpoint = child_harness(monkeypatch, late_stage=stage)
    budget = m._Budget(25, deadline_monotonic_ns=endpoint)
    with pytest.raises(m.PeerIdentityError):
        m._run_bounded(m._SYSCTL_BOOT_ID_ARGV, max_bytes=128, budget=budget)
    assert calls.count("spawn") == 1
    assert calls.count("cleanup") == 1
    if stage == "select":
        assert "read" not in calls


def test_expired_child_budget_does_not_spawn(monkeypatch):
    now, calls, endpoint = child_harness(monkeypatch)
    budget = m._Budget(25, deadline_monotonic_ns=endpoint)
    now[0] = endpoint
    with pytest.raises(m.PeerIdentityError):
        m._run_bounded(m._SYSCTL_BOOT_ID_ARGV, max_bytes=128, budget=budget)
    assert calls == []


def test_child_success_retains_closed_command_and_single_cleanup(monkeypatch):
    now, calls, endpoint = child_harness(monkeypatch)
    budget = m._Budget(25, deadline_monotonic_ns=endpoint)
    assert m._run_bounded(m._SYSCTL_BOOT_ID_ARGV, max_bytes=128, budget=budget) == b"ok\n"
    assert calls.count("spawn") == calls.count("cleanup") == 1


@pytest.mark.parametrize("cleanup_ok,code", [(True, "SERVICE_LAUNCHCTL_COMMAND_FAILED"), (False, "SERVICE_LAUNCHCTL_CLEANUP_UNPROVEN")])
def test_child_original_failure_and_cleanup_precedence(monkeypatch, cleanup_ok, code):
    now, calls, endpoint = child_harness(monkeypatch, failure_stage="read", cleanup_ok=cleanup_ok)
    budget = m._Budget(25, deadline_monotonic_ns=endpoint)
    with pytest.raises(m.PeerIdentityError) as failure:
        m._run_bounded(m._SYSCTL_BOOT_ID_ARGV, max_bytes=128, budget=budget)
    assert failure.value.code == code
    assert calls.count("cleanup") == 1


@pytest.mark.parametrize("step_ns,expires", [(1_000_000_000, False), (2_000_000_000, True)])
def test_repeated_identity_probes_share_one_cumulative_budget(monkeypatch, composition, step_ns, expires):
    value = composition("control")
    now, _ = clock(monkeypatch)
    calls = []
    old_boot = m._observe_real_boot_id
    old_launch = m._observe_launchd_service
    def boot(*, budget):
        calls.append(("boot", budget))
        now[0] += step_ns
        return old_boot()
    def launch(role, *, budget):
        calls.append(("launch", budget))
        now[0] += step_ns
        return old_launch(role)
    monkeypatch.setattr(m, "_observe_real_boot_id", boot)
    monkeypatch.setattr(m, "_observe_launchd_service", launch)
    if expires:
        with pytest.raises(m.PeerIdentityError):
            m._qualify_installed_peer_with_deadline(value.peer, role="control", deadline_monotonic_ns=10_000_000_000)
        assert [x[0] for x in calls] == ["boot", "launch", "boot", "launch", "boot"]
    else:
        binding = m._qualify_installed_peer_with_deadline(value.peer, role="control", deadline_monotonic_ns=10_000_000_000)
        context = m._peer_identity.require_installed_service_peer(value.peer, binding)
        assert context.connection_instance is value.peer.connection_instance
        assert context.service_label == value.launch.service_label
        assert [x[0] for x in calls] == ["boot", "launch"] * 3
    assert all(item[1] is calls[0][1] for item in calls)


@pytest.mark.parametrize("which", ["capture", "dynamic"])
def test_slow_synchronous_identity_observation_never_qualifies(monkeypatch, composition, which):
    value = composition("control")
    now, _ = clock(monkeypatch)
    old_boot = m._observe_real_boot_id
    old_launch = m._observe_launchd_service
    monkeypatch.setattr(m, "_observe_real_boot_id", lambda *, budget: old_boot())
    monkeypatch.setattr(m, "_observe_launchd_service", lambda role, *, budget: old_launch(role))
    owner = m._peer_identity if which == "capture" else m
    name = "_current_capture" if which == "capture" else "_observe_dynamic_code"
    old = getattr(owner, name)
    def slow(*args):
        result = old(*args)
        now[0] = 2_000_000_000
        return result
    monkeypatch.setattr(owner, name, slow)
    monkeypatch.setattr(m, "_owner_binding", lambda *a: pytest.fail("late observation reached binding"))
    with pytest.raises(m.PeerIdentityError):
        m._qualify_installed_peer_with_deadline(value.peer, role="control", deadline_monotonic_ns=2_000_000_000)


@pytest.mark.parametrize("stage", ["spawn", "select", "read", "poll", "cleanup"])
def test_codesign_child_uses_same_endpoint_and_cleanup(monkeypatch, stage):
    now, calls, endpoint = child_harness(monkeypatch, late_stage=stage)
    budget = m._Budget(25, deadline_monotonic_ns=endpoint)
    with pytest.raises(m.PeerIdentityError):
        m._run_bounded_readonly(m._CODESIGN_VERIFY_ARGV, budget=budget,
            max_bytes=128, allow_empty=True, merge_stderr=False)
    assert calls.count("spawn") == calls.count("cleanup") == 1
    if stage == "select":
        assert "read" not in calls


@pytest.mark.parametrize("which", ["pid", "program", "argv", "working_directory"])
def test_private_deadline_preserves_closed_identity_joins(monkeypatch, composition, which):
    value = composition("control")
    clock(monkeypatch)
    old_boot = m._observe_real_boot_id
    changes = {"pid": value.peer.pid + 1, "program": "/unqualified/python",
               "argv": value.launch.argv + ("--unqualified",), "working_directory": "/unqualified"}
    bad = dataclasses.replace(value.launch, **{which: changes[which]})
    monkeypatch.setattr(m, "_observe_real_boot_id", lambda *, budget: old_boot())
    monkeypatch.setattr(m, "_observe_launchd_service", lambda role, *, budget: bad)
    monkeypatch.setattr(m, "_owner_binding", lambda *a: pytest.fail("identity mismatch reached binding"))
    with pytest.raises(m.PeerIdentityError) as failure:
        m._qualify_installed_peer_with_deadline(value.peer, role="control", deadline_monotonic_ns=10_000_000_000)
    assert "MISMATCH" in failure.value.code


@pytest.mark.parametrize("change", ["pid", "pidversion"])
def test_private_deadline_does_not_hide_reused_or_execed_peer(monkeypatch, composition, change):
    value = composition("control")
    clock(monkeypatch)
    kernel = m._peer_identity._observe_socket(value.connection)
    changed = dataclasses.replace(kernel, **{change: getattr(kernel, change) + 1})
    monkeypatch.setattr(m._peer_identity, "_observe_socket", lambda connection: changed)
    monkeypatch.setattr(m, "_qualify", lambda *a: pytest.fail("stale capture reached qualification"))
    with pytest.raises(m.PeerIdentityError):
        m._qualify_installed_peer_with_deadline(value.peer, role="control", deadline_monotonic_ns=10_000_000_000)


@pytest.mark.parametrize("helper", ["read", "inventory"])
def test_private_file_refusal_survives_deadline_during_cleanup(monkeypatch, helper):
    now, _ = clock(monkeypatch)
    budget = m._Budget(25, deadline_monotonic_ns=2_000_000_000)
    info = SimpleNamespace(st_mode=stat.S_IFIFO, st_nlink=1, st_size=0)
    monkeypatch.setattr(m, "_open_trusted", lambda *a, **k: (123, info, info))
    closed = []
    def close(fd):
        closed.append(fd)
        now[0] = 2_000_000_000
    monkeypatch.setattr(m, "_close", close)
    if helper == "read":
        expected = "SERVICE_OBJECT_TYPE_UNSUPPORTED"
        call = lambda: m._read_trusted_bytes("/fixed", budget=budget, maximum=100)
    else:
        expected = "SERVICE_RUNTIME_BASE_UNQUALIFIED"
        monkeypatch.setattr(m, "_PYTHON_LINK_INDEX", {})
        call = lambda: m._inventory_python_base(budget)
    with pytest.raises(m.PeerIdentityError) as failure:
        call()
    assert failure.value.code == expected
    assert closed == [123]


def test_private_reap_sleep_is_clamped_and_late_exit_refuses(monkeypatch):
    now, sleeps = clock(monkeypatch)
    budget = m._Budget(25, deadline_monotonic_ns=1_001_000_000)
    class Child:
        def poll(self):
            return None
    assert m._reap_bounded_exit_code(Child(), 4.0, budget=budget) is None
    assert sleeps == [.001]
    class LateExit:
        def poll(self):
            now[0] = 2_000_000_000
            return 0
    now[0] = 1_000_000_000
    budget = m._Budget(25, deadline_monotonic_ns=2_000_000_000)
    assert m._reap_bounded_exit_code(LateExit(), 4.0, budget=budget) is None


@pytest.mark.parametrize("observer", ["boot", "launchd"])
def test_private_observer_refuses_late_parsed_result(monkeypatch, observer):
    now, _ = clock(monkeypatch)
    budget = m._Budget(25, deadline_monotonic_ns=2_000_000_000)
    def run(argv, *, max_bytes, budget):
        assert budget.caller_deadline == 2_000_000_000
        if argv == m._SYSCTL_OSRELEASE_ARGV:
            return b"25.5.0\n"
        return _launchd_fixture() if observer == "launchd" else b"01234567-89ab-cdef-0123-456789abcdef\n"
    monkeypatch.setattr(m, "_run_bounded", run)
    if observer == "launchd":
        old = m._parse_launchctl_service
        def parse(*args, **kwargs):
            result = old(*args, **kwargs)
            now[0] = 2_000_000_000
            return result
        monkeypatch.setattr(m, "_parse_launchctl_service", parse)
        call = lambda: m._observe_launchd_service("control", budget=budget)
    else:
        old = m._bounded_single_line
        def parse(*args, **kwargs):
            result = old(*args, **kwargs)
            now[0] = 2_000_000_000
            return result
        monkeypatch.setattr(m, "_bounded_single_line", parse)
        call = lambda: m._observe_real_boot_id(budget=budget)
    with pytest.raises(m.PeerIdentityError):
        call()


def test_private_entry_requires_endpoint_even_though_budget_none_is_legacy(monkeypatch):
    def forbidden():
        pytest.fail("missing private endpoint read clock")
    monkeypatch.setattr(m, "time", SimpleNamespace(monotonic=forbidden, monotonic_ns=forbidden))
    with pytest.raises(m.PeerIdentityError, match="DEADLINE_INVALID"):
        m._qualify_installed_peer_with_deadline(object(), role="control", deadline_monotonic_ns=None)


@pytest.mark.parametrize("uid,expected", [(501, "SERVICE_OBJECT_NOT_ROOT_OWNED"), (0, "SERVICE_QUALIFICATION_BUDGET_EXCEEDED")])
def test_private_late_metadata_refusal_is_preserved_without_next_open(monkeypatch, uid, expected):
    now, _ = clock(monkeypatch)
    budget = m._Budget(25, deadline_monotonic_ns=2_000_000_000)
    def lstat(path):
        now[0] = 2_000_000_000
        return SimpleNamespace(st_uid=uid, st_gid=0, st_mode=stat.S_IFREG | 0o600)
    monkeypatch.setattr(m, "_lstat", lstat)
    fake_os = SimpleNamespace(**vars(os))
    fake_os.open = lambda *a: pytest.fail("late metadata initiated another open")
    monkeypatch.setattr(m, "os", fake_os)
    with pytest.raises(m.PeerIdentityError) as failure:
        m._open_trusted("/fixed", budget=budget)
    assert failure.value.code == expected
