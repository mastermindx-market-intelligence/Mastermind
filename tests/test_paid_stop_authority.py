"""Offline mechanics tests for the paid-stop receipt authority.

Every test except the seam-disclosure test runs on an inert ``_SYSCALLS``
replacement.  No fixture asserts live authorization: no real euid 0, no real
Darwin boot identifier, no real ``/var/db`` receipt, no live peer capture.
"""

from __future__ import annotations

import copy
import datetime as dt
import gc
import hashlib
import json
import os
import pickle
import re
import stat
import uuid
from types import SimpleNamespace

import pytest

from control_plane import paid_stop_authority as psa

REQUEST_ID = "stop-paid-0001"
RELEASE_SHA = "b" * 40
DEFINITION_SHA = "c" * 64
BOOT_ID = str(uuid.UUID(int=0x1F5A3C9E8F2B4C6D9A7E2B3C4D5E6F70))
OTHER_UUID = str(uuid.UUID(int=0x2F5A3C9E8F2B4C6D9A7E2B3C4D5E6F70))
DELETE = object()
_UNSET = object()
_REFUSAL_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def install_seam(kernel):
    psa._SYSCALLS = psa._Syscalls(
        dup=kernel.dup,
        close=kernel.close,
        getpid=kernel.getpid,
        getfl=kernel.getfl,
        getpath=kernel.getpath,
        setfd_cloexec=kernel.setfd_cloexec,
        fstat=kernel.fstat,
        pread=kernel.pread,
        capture_peer=kernel.capture_peer,
        verify_peer=kernel.verify_peer,
        boot_session_id=kernel.boot_session_id,
    )


def now_stamp(offset: float = 0.0) -> str:
    moment = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=offset)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def make_intent(request_id=REQUEST_ID, release=RELEASE_SHA, definition=DEFINITION_SHA, request_sha=None):
    base = hashlib.sha256(
        psa.canonical_paid_stop_request(
            psa.StopIntent(request_id, "0" * 64, release, definition)
        )
    ).hexdigest()
    return psa.StopIntent(request_id, request_sha or base, release, definition)


def marker_for(intent, started=None, **over):
    marker = {
        "schema": psa.INFLIGHT_SCHEMA,
        "request_id": intent.request_id,
        "request_sha256": intent.request_sha256,
        "action": psa.PAID_STOP_ACTION,
        "effect_class": psa.PAID_STOP_EFFECT_CLASS,
        "started_at": started or now_stamp(),
        "release_sha": intent.release_sha,
    }
    for key, value in over.items():
        if value is DELETE:
            marker.pop(key, None)
        else:
            marker[key] = value
    return json.dumps(marker, sort_keys=True).encode("utf-8")


def receipt_path_for(request_id=REQUEST_ID):
    return psa.RECEIPT_DIR + "/" + request_id + ".json"


class FakePeer:
    def __init__(self):
        self.pid = 411
        self.pidversion = 9
        self.euid = 0
        self.audit_identity_digest = "d" * 64


class FakeConnection:
    pass


class ReceiptFile:
    def __init__(self, content, path, flags=os.O_RDONLY, mode=0o600, uid=0, gid=0,
                 nlink=1, regular=True, dev=1, ino=7777):
        self.content = content
        self.path = path
        self.flags = flags
        self.mode = mode
        self.uid = uid
        self.gid = gid
        self.nlink = nlink
        self.regular = regular
        self.dev = dev
        self.ino = ino
        self.mtime_ns = 1_700_000_000_000_000_000
        self.ctime_ns = 1_700_000_000_000_000_001
        self.size_delta = 0
        self.flaky = False
        self._flip = False

    def stat_ns(self):
        base = (stat.S_IFREG if self.regular else stat.S_IFDIR) | self.mode
        return SimpleNamespace(
            st_dev=self.dev,
            st_ino=self.ino,
            st_mode=base,
            st_nlink=self.nlink,
            st_uid=self.uid,
            st_gid=self.gid,
            st_size=len(self.content) + self.size_delta,
            st_mtime_ns=self.mtime_ns,
            st_ctime_ns=self.ctime_ns,
        )

    def read(self, count, offset):
        self._flip = not self._flip
        data = self.content
        if self.flaky and self._flip:
            data = data + b" "
        return data[offset:offset + count]


class FakeKernel:
    real_dup = False

    def __init__(self, receipt, peer, boot_id=BOOT_ID, pid=1234):
        self.receipt = receipt
        self.peer = peer
        self.boot_id = boot_id
        self.pid = pid
        self.next_fd = 1000
        self.table = {}
        self.dups = 0
        self.closes = 0
        self.fail_getpath = False
        self._peer_snapshot = None

    def register(self, fd, receipt):
        self.table[fd] = receipt
        return fd

    def _entry(self, fd):
        if fd not in self.table:
            raise OSError(9, "bad descriptor")
        return self.table[fd]

    def dup(self, fd):
        entry = self._entry(fd)
        self.dups += 1
        self.next_fd += 1
        self.table[self.next_fd] = entry
        return self.next_fd

    def close(self, fd):
        self._entry(fd)
        self.closes += 1
        del self.table[fd]

    def getpid(self):
        return self.pid

    def getfl(self, fd):
        return self._entry(fd).flags

    def getpath(self, fd):
        if self.fail_getpath:
            raise OSError(45, "no path")
        return self._entry(fd).path

    def setfd_cloexec(self, fd):
        return None

    def fstat(self, fd):
        return self._entry(fd).stat_ns()

    def pread(self, fd, count, offset):
        return self._entry(fd).read(count, offset)

    def capture_peer(self, connection):
        if not isinstance(connection, FakeConnection):
            raise OSError(57, "not a socket")
        return self.peer

    def verify_peer(self, peer):
        if peer is None or peer is not self.peer:
            raise psa.PaidStopAuthorityError("PEER_IDENTITY_CHANGED")
        fields = (peer.pid, peer.pidversion, peer.euid, peer.audit_identity_digest)
        if self._peer_snapshot is None:
            self._peer_snapshot = fields
        elif fields != self._peer_snapshot:
            raise psa.PaidStopAuthorityError("PEER_IDENTITY_CHANGED")
        return peer

    def boot_session_id(self):
        return self.boot_id


class World:
    def __init__(self, receipt=None, kernel=None, intent=None):
        self.intent = intent or make_intent()
        self.receipt = receipt or ReceiptFile(
            marker_for(self.intent), receipt_path_for()
        )
        self.kernel = kernel or FakeKernel(self.receipt, FakePeer())
        self.connection = FakeConnection()

    def qualify(self, intent=_UNSET, fd=1000, connection=None, register=True):
        if register:
            self.kernel.register(fd, self.receipt)
        return psa.qualify_stop_receipt(
            fd,
            connection if connection is not None else self.connection,
            stop_intent=self.intent if intent is _UNSET else intent,
        )


@pytest.fixture
def world():
    created = World()
    original = psa._SYSCALLS
    install_seam(created.kernel)
    try:
        yield created
    finally:
        psa._SYSCALLS = original


def refusal(call, code):
    with pytest.raises(psa.PaidStopAuthorityError) as caught:
        call()
    assert caught.value.code == code
    assert str(caught.value) == code
    return caught.value


# ------------------------------------------------------- seam disclosure ----
def test_default_seam_is_real_and_live_capture_is_refused():
    assert psa._SYSCALLS is psa._REAL_SYSCALLS
    assert psa._REAL_SYSCALLS.dup is os.dup
    assert psa._REAL_SYSCALLS.close is os.close
    assert psa._REAL_SYSCALLS.getpid is os.getpid
    assert psa._REAL_SYSCALLS.fstat is os.fstat
    disclosed = {
        "BROKER_PEER_UNAVAILABLE",
        "PEER_PRIMITIVE_UNAVAILABLE",
        "PEER_PLATFORM_UNSUPPORTED",
        "PEER_SOCKET_REQUIRED",
        "PEER_UNIX_STREAM_REQUIRED",
        "PEER_KERNEL_IDENTITY_UNAVAILABLE",
        "PEER_AUDIT_API_UNAVAILABLE",
    }
    with pytest.raises(psa.PaidStopAuthorityError) as caught:
        psa.qualify_stop_receipt(0, object(), stop_intent=make_intent())
    assert caught.value.code in disclosed
    assert str(caught.value) == caught.value.code


# ------------------------------------------------------------- success ----
def test_qualify_then_require_returns_exact_observation(world):
    authority = world.qualify()
    observation = psa.require_stop_authority(authority, stop_intent=world.intent)
    peer = world.kernel.peer
    assert observation.broker_process == psa._BrokerProcess(
        pid=peer.pid,
        pidversion=peer.pidversion,
        euid=0,
        audit_identity_digest=peer.audit_identity_digest,
        boot_id=BOOT_ID,
    )
    assert observation.receipt_sha256 == hashlib.sha256(world.receipt.content).hexdigest()
    identity = observation.receipt_identity
    assert (identity.device, identity.inode, identity.mode, identity.uid, identity.gid) == (
        world.receipt.dev,
        world.receipt.ino,
        stat.S_IFREG | 0o600,
        0,
        0,
    )
    assert (identity.size, identity.mtime_ns, identity.ctime_ns) == (
        len(world.receipt.content),
        world.receipt.mtime_ns,
        world.receipt.ctime_ns,
    )
    assert observation.stop_intent == world.intent


def test_observation_shape_and_redaction(world):
    observation = psa.require_stop_authority(world.qualify(), stop_intent=world.intent)
    dump = json.dumps(observation.to_dict())
    assert set(observation.to_dict()) == {
        "broker_process",
        "receipt_sha256",
        "receipt_identity",
        "stop_intent",
    }
    assert set(observation.to_dict()["broker_process"]) == {
        "pid",
        "pidversion",
        "euid",
        "audit_identity_digest",
        "boot_id",
    }
    assert set(observation.to_dict()["receipt_identity"]) == {
        "device",
        "inode",
        "mode",
        "uid",
        "gid",
        "size",
        "mtime_ns",
        "ctime_ns",
    }
    assert set(observation.to_dict()["stop_intent"]) == {
        "request_id",
        "request_sha256",
        "release_sha",
        "expected_definition_sha256",
    }
    assert psa.RECEIPT_DIR not in dump
    assert receipt_path_for() not in dump
    assert world.receipt.path not in dump
    assert "started_at" not in dump
    assert world.receipt.content.decode() not in dump
    assert dump == json.dumps(observation.to_dict())


def test_canonical_request_reconstruction_is_exact():
    intent = make_intent()
    assert psa.canonical_paid_stop_request(intent) == (
        '{"action":"executive.services.stop_paid",'
        '"args":{"expected_definition_sha256":"' + DEFINITION_SHA + '"},'
        '"request_id":"' + REQUEST_ID + '",'
        '"schema":"mastermind.executive_privileged_action_request.v1"}\n'
    ).encode("ascii")
    assert hashlib.sha256(psa.canonical_paid_stop_request(intent)).hexdigest() == (
        intent.request_sha256
    )


# ------------------------------------------------------- intent refusal ----
@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"request_id": "../etc/passwd"}, "STOP_INTENT_REQUEST_ID_INVALID"),
        ({"request_id": "has/slash"}, "STOP_INTENT_REQUEST_ID_INVALID"),
        ({"request_id": "ab"}, "STOP_INTENT_REQUEST_ID_INVALID"),
        ({"release": "z" * 64}, "STOP_INTENT_DIGEST_INVALID"),
        ({"release": "B" * 64}, "STOP_INTENT_DIGEST_INVALID"),
        ({"definition": "c" * 63}, "STOP_INTENT_DIGEST_INVALID"),
        ({"request_sha": "0" * 64}, "STOP_INTENT_REQUEST_DIGEST_MISMATCH"),
    ],
)
def test_intent_field_refusals(world, kwargs, code):
    refusal(lambda: world.qualify(intent=make_intent(**kwargs)), code)


def test_intent_request_digest_must_match_reconstruction(world):
    refusal(lambda: world.qualify(intent=make_intent(request_sha="0" * 64)),
            "STOP_INTENT_REQUEST_DIGEST_MISMATCH")


def test_intent_keyset_and_type_refusals(world):
    refusal(lambda: world.qualify(intent={"schema": "x"}), "STOP_INTENT_KEYS_INVALID")
    extra = dict(world.intent.to_dict())
    extra["receipt_path"] = receipt_path_for()
    refusal(lambda: world.qualify(intent=extra), "STOP_INTENT_KEYS_INVALID")
    missing = dict(world.intent.to_dict())
    missing.pop("release_sha")
    refusal(lambda: world.qualify(intent=missing), "STOP_INTENT_KEYS_INVALID")
    refusal(lambda: world.qualify(intent=None), "STOP_INTENT_REQUIRED")
    refusal(lambda: world.qualify(intent=42), "STOP_INTENT_REQUIRED")
    broken = world.intent.to_dict()
    broken["request_id"] = 7
    refusal(lambda: world.qualify(intent=broken), "STOP_INTENT_TYPES_INVALID")


# -------------------------------------------------- descriptor refusal ----
def test_missing_and_malformed_fd_refusals(world):
    refusal(lambda: world.qualify(fd=9999, register=False),
            "RECEIPT_FD_DUP_UNAVAILABLE")
    refusal(lambda: world.qualify(fd=-1, register=False), "RECEIPT_FD_REQUIRED")
    refusal(lambda: world.qualify(fd="1000", register=False), "RECEIPT_FD_REQUIRED")
    refusal(lambda: world.qualify(fd=True, register=False), "RECEIPT_FD_REQUIRED")
    refusal(lambda: world.qualify(fd=None, register=False), "RECEIPT_FD_REQUIRED")


@pytest.mark.parametrize(
    "flags,code",
    [
        (os.O_RDWR, "RECEIPT_FD_NOT_READ_ONLY"),
        (os.O_WRONLY, "RECEIPT_FD_NOT_READ_ONLY"),
        (os.O_RDONLY | os.O_APPEND, "RECEIPT_FD_WRITABLE"),
    ],
)
def test_writable_fd_refusals(world, flags, code):
    world.receipt.flags = flags
    refusal(lambda: world.qualify(), code)


def test_getpath_failure_refusal(world):
    world.kernel.fail_getpath = True
    refusal(lambda: world.qualify(), "RECEIPT_PATH_UNAVAILABLE")


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda r: setattr(r, "mode", 0o644), "RECEIPT_MODE_INVALID"),
        (lambda r: setattr(r, "mode", 0o666), "RECEIPT_MODE_INVALID"),
        (lambda r: setattr(r, "mode", 0o700), "RECEIPT_MODE_INVALID"),
        (lambda r: setattr(r, "uid", 1000), "RECEIPT_OWNERSHIP_INVALID"),
        (lambda r: setattr(r, "gid", 1000), "RECEIPT_OWNERSHIP_INVALID"),
        (lambda r: setattr(r, "nlink", 2), "RECEIPT_LINK_COUNT_INVALID"),
        (lambda r: setattr(r, "regular", False), "RECEIPT_NOT_REGULAR"),
    ],
)
def test_identity_field_refusals(world, mutate, code):
    mutate(world.receipt)
    refusal(lambda: world.qualify(), code)


@pytest.mark.parametrize(
    "content,code",
    [
        (b"", "RECEIPT_SIZE_OUT_OF_BOUNDS"),
        (b"x" * (psa._MAX_RECEIPT_BYTES + 1), "RECEIPT_SIZE_OUT_OF_BOUNDS"),
    ],
)
def test_size_bounds_refusals(world, content, code):
    world.receipt.content = content
    refusal(lambda: world.qualify(), code)


def test_unstable_identity_refusal(world):
    class DriftingKernel(FakeKernel):
        def fstat(self, fd):
            entry = self._entry(fd)
            if getattr(entry, "drift", False):
                entry.drift_ticks = getattr(entry, "drift_ticks", 0) + 1
            ns = entry.stat_ns()
            ns.st_mtime_ns += getattr(entry, "drift_ticks", 0)
            return ns

    world.receipt.drift = True
    world.kernel = DriftingKernel(world.receipt, world.kernel.peer)
    install_seam(world.kernel)
    refusal(lambda: world.qualify(), "RECEIPT_IDENTITY_UNSTABLE")


def test_unstable_content_refusal(world):
    world.receipt.flaky = True
    refusal(lambda: world.qualify(), "RECEIPT_CONTENT_UNSTABLE")


@pytest.mark.parametrize(
    "content,code",
    [
        (b"{", "RECEIPT_MARKER_MALFORMED"),
        (b"[]", "RECEIPT_MARKER_NOT_OBJECT"),
        (b"null", "RECEIPT_MARKER_NOT_OBJECT"),
        (b'{"schema":"x"}', "RECEIPT_MARKER_KEYS_INVALID"),
        (b"\x00{}", "RECEIPT_CONTENT_NOT_TEXT"),
        (b'{"schema": "\xff"}', "RECEIPT_CONTENT_NOT_UTF8"),
    ],
)
def test_malformed_marker_refusals(world, content, code):
    world.receipt.content = content
    refusal(lambda: world.qualify(), code)


@pytest.mark.parametrize(
    "over,code",
    [
        ({"schema": psa.REQUEST_SCHEMA}, "RECEIPT_MARKER_SCHEMA_INVALID"),
        ({"schema": "mastermind.executive_privileged_action_inflight.v2"},
         "RECEIPT_MARKER_SCHEMA_INVALID"),
        ({"action": "executive.services.stop"}, "RECEIPT_MARKER_ACTION_INVALID"),
        ({"action": "executive.services.start_paid"}, "RECEIPT_MARKER_ACTION_INVALID"),
        ({"effect_class": "HOST_POWER_POLICY"}, "RECEIPT_MARKER_EFFECT_CLASS_INVALID"),
        ({"effect_class": "CREDENTIAL_ADMIN_READINESS"},
         "RECEIPT_MARKER_EFFECT_CLASS_INVALID"),
        ({"request_id": "stop-paid-0002"}, "RECEIPT_REQUEST_IDENTITY_MISMATCH"),
        ({"release_sha": "a" * 64}, "RECEIPT_RELEASE_MISMATCH"),
        ({"request_sha256": "a" * 64}, "RECEIPT_REQUEST_DIGEST_MISMATCH"),
        ({"started_at": "2026-10-22 15:00:00"}, "RECEIPT_STARTED_AT_INVALID"),
        ({"started_at": "2026-02-30T00:00:00Z"}, "RECEIPT_STARTED_AT_INVALID"),
        ({"started_at": "2026-10-22T15:00:00.5Z"}, "RECEIPT_STARTED_AT_INVALID"),
        ({"extra": 1}, "RECEIPT_MARKER_KEYS_INVALID"),
        ({"release_sha": DELETE}, "RECEIPT_MARKER_KEYS_INVALID"),
    ],
)
def test_marker_field_refusals(world, over, code):
    world.receipt.content = marker_for(world.intent, **over)
    refusal(lambda: world.qualify(), code)


def test_receipt_path_namespace_locked(world):
    other_id = "stop-paid-0002"
    other_intent = make_intent(request_id=other_id)
    world.receipt = ReceiptFile(marker_for(other_intent), receipt_path_for())
    refusal(lambda: world.qualify(intent=other_intent), "RECEIPT_PATH_MISMATCH")
    world.receipt.path = "/tmp/" + other_id + ".json"
    refusal(lambda: world.qualify(intent=other_intent), "RECEIPT_PATH_MISMATCH")


# ------------------------------------------------------- broker refusal ----
@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda p: setattr(p, "euid", 501), "BROKER_PEER_NOT_ROOT"),
        (lambda p: setattr(p, "pid", 0), "BROKER_PEER_NOT_ROOT"),
        (lambda p: setattr(p, "pidversion", -1), "BROKER_PEER_NOT_ROOT"),
        (lambda p: setattr(p, "audit_identity_digest", "nope"), "BROKER_PEER_FIELDS_INVALID"),
    ],
)
def test_broker_peer_refusals(world, mutate, code):
    mutate(world.kernel.peer)
    refusal(lambda: world.qualify(), code)


@pytest.mark.parametrize(
    "boot,code",
    [
        ("not-a-uuid", "BOOT_IDENTITY_INVALID"),
        ("00000000-0000-0000-0000-000000000000", "BOOT_IDENTITY_INVALID"),
        (None, "BOOT_IDENTITY_UNAVAILABLE"),
    ],
)
def test_boot_identity_refusals(world, boot, code):
    world.kernel.boot_id = boot
    refusal(lambda: world.qualify(), code)


# ---------------------------------------------- forge and serialization ----
def test_authority_cannot_be_constructed_or_serialized(world):
    with pytest.raises(psa.PaidStopAuthorityError) as caught:
        psa.PaidStopAuthority()
    assert caught.value.code == "STOP_AUTHORITY_CONSTRUCTION_PRIVATE"
    authority = world.qualify()
    with pytest.raises(Exception):
        pickle.dumps(authority)
    with pytest.raises(Exception):
        copy.copy(authority)
    with pytest.raises(Exception):
        copy.deepcopy(authority)
    del authority
    gc.collect()


def test_require_refuses_forged_and_inert_objects(world):
    authority = world.qualify()
    refusal(lambda: psa.require_stop_authority(object(), stop_intent=world.intent),
            "STOP_AUTHORITY_PROVENANCE_REQUIRED")
    refusal(lambda: psa.require_stop_authority(None, stop_intent=world.intent),
            "STOP_AUTHORITY_PROVENANCE_REQUIRED")
    forged = psa.StopAuthorityObservation(
        broker_process=psa._BrokerProcess(411, 9, 0, "d" * 64, BOOT_ID),
        receipt_sha256=hashlib.sha256(world.receipt.content).hexdigest(),
        receipt_identity=psa._ReceiptIdentity(1, 7777, stat.S_IFREG | 0o600, 0, 0,
                                              len(world.receipt.content),
                                              world.receipt.mtime_ns,
                                              world.receipt.ctime_ns),
        stop_intent=world.intent,
    )
    json.dumps(forged.to_dict())  # detached data is serializable by design
    refusal(lambda: psa.require_stop_authority(forged, stop_intent=world.intent),
            "STOP_AUTHORITY_PROVENANCE_REQUIRED")
    refusal(lambda: psa.require_stop_authority(type("X", (), {})(),
                                               stop_intent=world.intent),
            "STOP_AUTHORITY_PROVENANCE_REQUIRED")
    del authority
    gc.collect()


def test_require_intent_mismatch(world):
    authority = world.qualify()
    other = make_intent(request_id="stop-paid-0003")
    refusal(lambda: psa.require_stop_authority(authority, stop_intent=other),
            "STOP_AUTHORITY_INTENT_MISMATCH")
    del authority


def test_require_after_finalization_refuses(world):
    authority = world.qualify()
    del authority
    gc.collect()
    refusal(lambda: psa.require_stop_authority(object(), stop_intent=world.intent),
            "STOP_AUTHORITY_PROVENANCE_REQUIRED")


# ------------------------------------------------------- consume drift ----
def test_receiver_process_drift_refused(world):
    authority = world.qualify()
    world.kernel.pid = 999999
    refusal(lambda: psa.require_stop_authority(authority, stop_intent=world.intent),
            "STOP_AUTHORITY_PROCESS_CHANGED")


def test_peer_identity_drift_refused(world):
    authority = world.qualify()
    world.kernel.peer.pid = 424242
    refusal(lambda: psa.require_stop_authority(authority, stop_intent=world.intent),
            "PEER_IDENTITY_CHANGED")


def test_boot_drift_refused(world):
    authority = world.qualify()
    world.kernel.boot_id = OTHER_UUID
    refusal(lambda: psa.require_stop_authority(authority, stop_intent=world.intent),
            "STOP_AUTHORITY_BOOT_CHANGED")


def test_connection_and_peer_garbage_collected_refused(world):
    authority = world.qualify()
    world.connection = None
    gc.collect()
    refusal(lambda: psa.require_stop_authority(authority, stop_intent=world.intent),
            "STOP_AUTHORITY_CONNECTION_CLOSED")


def test_receipt_generation_drift_refused(world):
    authority = world.qualify()
    world.receipt.content = world.receipt.content + b" "
    refusal(lambda: psa.require_stop_authority(authority, stop_intent=world.intent),
            "RECEIPT_GENERATION_DRIFT")


def test_receipt_stat_drift_refused(world):
    authority = world.qualify()
    world.receipt.size_delta = 1
    refusal(lambda: psa.require_stop_authority(authority, stop_intent=world.intent),
            "RECEIPT_GENERATION_DRIFT")


def test_changed_started_at_refused_as_receipt_generation_drift(world):
    authority = world.qualify()
    world.receipt.content = marker_for(world.intent, started=now_stamp(-90000))
    refusal(lambda: psa.require_stop_authority(authority, stop_intent=world.intent),
            "RECEIPT_GENERATION_DRIFT")


# ------------------------------------------------------ fd ownership ----
def test_owned_descriptor_is_private_dup_not_caller_fd(world, tmp_path):
    path = tmp_path / "receipt.json"
    baseline = len(os.listdir("/dev/fd"))
    path.write_bytes(world.receipt.content);path.chmod(0o600)
    real_fd = os.open(path, os.O_RDONLY)
    original_dup, original_close = world.kernel.dup, world.kernel.close
    try:
        world.kernel.table = {real_fd: world.receipt}

        def real_dup(fd):
            new_fd = os.dup(fd)
            world.kernel.table[new_fd] = world.kernel.table[fd]
            world.kernel.dups += 1
            return new_fd

        def real_close(fd):
            world.kernel.closes += 1
            os.close(fd)
            world.kernel.table.pop(fd, None)

        world.kernel.dup, world.kernel.close = real_dup, real_close
        install_seam(world.kernel)
        authority = world.qualify(fd=real_fd)
        os.close(real_fd)  # caller may close after handing over the descriptor
        observation = psa.require_stop_authority(authority, stop_intent=world.intent)
        assert observation.receipt_sha256 == hashlib.sha256(world.receipt.content).hexdigest()
        del authority
        gc.collect()
        assert len(os.listdir("/dev/fd")) == baseline
        assert world.kernel.closes >= 1
    finally:
        world.kernel.dup, world.kernel.close = original_dup, original_close
        install_seam(world.kernel)
        world.kernel.table.pop(real_fd, None)
        try:
            os.close(real_fd)
        except OSError:
            pass


def test_no_descriptor_leak_across_many_qualifications(world):
    for _ in range(50):
        authority = world.qualify()
        del authority
    gc.collect()
    assert world.kernel.dups == world.kernel.closes
    assert set(world.kernel.table) == {1000}


def test_refusals_never_disclose_receipt_material(world):
    secret_marker = world.receipt.content
    failures = []
    for call, _code in [
        (lambda: world.qualify(fd=9999), "RECEIPT_FD_DUP_UNAVAILABLE"),
        (lambda: world.qualify(intent=make_intent(request_sha="0" * 64)),
         "STOP_INTENT_REQUEST_DIGEST_MISMATCH"),
        (lambda: world.qualify(intent={"schema": "x"}), "STOP_INTENT_KEYS_INVALID"),
    ]:
        try:
            call()
        except psa.PaidStopAuthorityError as exc:
            failures.append(exc)
    assert failures
    for exc in failures:
        assert str(exc) == exc.code
        assert _REFUSAL_RE.fullmatch(exc.code) is not None
        assert secret_marker not in exc.args
        assert receipt_path_for() not in str(exc)
        assert psa.RECEIPT_DIR not in str(exc)


def test_real_canonical_request_and_release_width_match_incumbent_owner():
    from control_plane.executive_privileged_action import validate_request,canonical_request_bytes
    intent=make_intent()
    actual=validate_request({'schema':psa.REQUEST_SCHEMA,'request_id':intent.request_id,
        'action':psa.PAID_STOP_ACTION,'args':{'expected_definition_sha256':intent.expected_definition_sha256}})
    assert len(intent.release_sha)==40
    assert psa.canonical_paid_stop_request(intent)==canonical_request_bytes(actual)
    assert psa.RECEIPT_DIR=='/private/var/db/mastermind-executive/privileged-actions/receipts/inflight'


def test_reference_boot_adapter_invokes_actual_inspector_method(monkeypatch):
    from control_plane import codex_worker
    calls=[]
    class InertInspector:
        def boot_session_id(self):calls.append(1);return BOOT_ID
    monkeypatch.setattr(codex_worker,'ProcessInspector',InertInspector)
    assert psa._reference_boot_session_id()==BOOT_ID and calls==[1]


def test_authority_retains_its_captured_peer_until_finalization(world,monkeypatch):
    import dataclasses,weakref
    refs=[]
    def capture(connection):
        peer=FakePeer();refs.append(weakref.ref(peer));return peer
    def verify(peer):
        assert peer is refs[0]()  # inert lifetime assertion, never authentication
    monkeypatch.setattr(psa,'_SYSCALLS',dataclasses.replace(psa._SYSCALLS,capture_peer=capture,verify_peer=verify))
    authority=world.qualify();gc.collect()
    assert refs[0]() is not None
    assert psa.require_stop_authority(authority,stop_intent=world.intent).stop_intent==world.intent
    del authority;gc.collect()
    assert refs[0]() is None


@pytest.mark.parametrize('stamp',[now_stamp(-90000),now_stamp(3600)])
def test_existing_inflight_timestamp_has_no_invented_expiry(world,stamp):
    world.receipt.content=marker_for(world.intent,started=stamp)
    authority=world.qualify()
    assert psa.require_stop_authority(authority,stop_intent=world.intent).stop_intent==world.intent


def test_duplicate_marker_key_is_refused_not_silently_replaced(world):
    world.receipt.content=b'{"schema":"wrong",'+world.receipt.content[1:]
    refusal(lambda:world.qualify(),'RECEIPT_MARKER_MALFORMED')


def test_actual_darwin_uuid_case_is_preserved_not_made_incompatible(world):
    world.kernel.boot_id=BOOT_ID.upper()
    authority=world.qualify()
    result=psa.require_stop_authority(authority,stop_intent=world.intent)
    assert result.broker_process.boot_id==BOOT_ID.upper()
