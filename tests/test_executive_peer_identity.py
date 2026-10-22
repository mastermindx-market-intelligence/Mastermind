"""Kernel capture and opaque binding boundaries; no live release authority."""

from __future__ import annotations

import copy
import os
import socket
import subprocess
import sys
import tempfile
from dataclasses import replace
import hashlib
import pickle

import pytest

from control_plane import executive_peer_identity as peer


def test_public_capture_cannot_be_constructed_from_fields():
    with pytest.raises(TypeError):
        peer.PeerIdentity(euid=0, pid=1, pidversion=1)


@pytest.mark.parametrize("value", [None, True, {}, {"euid": 0, "pid": 1}, 1, "root"])
def test_raw_data_is_never_captured_provenance(value):
    with pytest.raises(peer.PeerIdentityError) as caught:
        peer._current_capture(value)
    assert caught.value.code == "PEER_CAPTURE_PROVENANCE_REQUIRED"


def test_structurally_forged_capture_does_not_have_provenance():
    forged = object.__new__(peer.PeerIdentity)
    for name, value in dict(
        euid=0,
        pid=1,
        pidversion=1,
        audit_token=b"\0" * 32,
        audit_identity_digest="0" * 64,
        connection_instance=object(),
    ).items():
        object.__setattr__(forged, name, value)
    with pytest.raises(peer.PeerIdentityError) as caught:
        peer._current_capture(forged)
    assert caught.value.code == "PEER_CAPTURE_PROVENANCE_REQUIRED"


@pytest.mark.parametrize("raw", [b"", b"\0" * 31, b"\0" * 33, bytearray(32), None])
def test_audit_token_requires_exact_opaque_kernel_size(raw):
    with pytest.raises(peer.PeerIdentityError) as caught:
        peer._decode_audit(raw)
    assert caught.value.code == "PEER_AUDIT_TOKEN_INVALID"


@pytest.mark.parametrize(
    "values", [(0xFFFFFFFF, 1, 1), (0, 0, 1), (0, 1, 0), (0, -1, 1), (0, 1, -1)]
)
def test_audit_accessor_incomplete_identity_refuses(monkeypatch, values):
    monkeypatch.setattr(
        peer,
        "_darwin_accessors",
        lambda: (None, tuple((lambda _, n=n: n) for n in values)),
    )
    with pytest.raises(peer.PeerIdentityError) as caught:
        peer._decode_audit(b"\0" * 32)
    assert caught.value.code == "PEER_AUDIT_IDENTITY_INCOMPLETE"


def test_unsupported_platform_has_no_uid_only_fallback(monkeypatch):
    monkeypatch.setattr(peer.sys, "platform", "linux")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        with pytest.raises(peer.PeerIdentityError) as caught:
            peer.capture_peer_identity(connection)
    assert caught.value.code == "PEER_PLATFORM_UNSUPPORTED"


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin kernel primitive")
@pytest.mark.parametrize("value", [None, {}, {"euid": 501}, True, 1])
def test_uid_only_socket_mock_refuses(value):
    with pytest.raises(peer.PeerIdentityError) as caught:
        peer.capture_peer_identity(value)
    assert caught.value.code == "PEER_SOCKET_REQUIRED"


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin kernel primitive")
def test_unconnected_socket_refuses():
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        with pytest.raises(peer.PeerIdentityError):
            peer.capture_peer_identity(connection)


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin kernel primitive")
def test_other_socket_kinds_refuse():
    for family, kind in [
        (socket.AF_INET, socket.SOCK_STREAM),
        (socket.AF_UNIX, socket.SOCK_DGRAM),
    ]:
        with socket.socket(family, kind) as connection:
            with pytest.raises(peer.PeerIdentityError) as caught:
                peer.capture_peer_identity(connection)
            assert caught.value.code == "PEER_UNIX_STREAM_REQUIRED"


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin kernel primitive")
def test_real_kernel_capture_and_revalidation():
    first, second = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        captured = peer.capture_peer_identity(first)
        assert captured.pid == os.getpid()
        assert captured.euid == os.geteuid()
        assert captured.pidversion > 0
        assert len(captured.audit_token) == 32
        assert (
            captured.audit_identity_digest
            == hashlib.sha256(captured.audit_token).hexdigest()
        )
        assert captured.connection_instance is not None
        peer._current_capture(captured)
        with pytest.raises(TypeError):
            copy.deepcopy(captured)
        with pytest.raises(AttributeError):
            captured.euid = 0
    finally:
        first.close()
        second.close()
    with pytest.raises(peer.PeerIdentityError):
        peer._current_capture(captured)


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin kernel primitive")
def test_modified_public_capture_cannot_revalidate():
    first, second = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        captured = peer.capture_peer_identity(first)
        object.__setattr__(captured, "pid", captured.pid + 1)
        with pytest.raises(peer.PeerIdentityError) as caught:
            peer._current_capture(captured)
        assert caught.value.code == "PEER_CAPTURE_ALTERED"
    finally:
        first.close()
        second.close()


@pytest.fixture
def captured(monkeypatch):
    """Portable binding mechanics, explicitly NOT installed-service proof.

    Only this fixture substitutes the kernel observation. Native capture has
    separate actual Darwin tests above/below. No production factory is enabled.
    """
    first, second = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    observation = peer._KernelObservation(
        b"K" * 32, 501, 1234, 5678, peer._descriptor_identity(first)
    )
    monkeypatch.setattr(peer, "_observe_socket", lambda _: observation)
    try:
        yield peer.capture_peer_identity(first), first, observation
    finally:
        first.close()
        second.close()


def owner_observation(capture):
    """Private test composition only; hashes/boot are fixture observations."""
    return peer._QualifiedOwnerObservation(
        real_boot_id="11111111-1111-4111-8111-111111111111",
        audit_identity_digest=capture.audit_identity_digest,
        service_label="com.mastermind.executive.control",
        installed_release="a" * 40,
        config_digest="b" * 64,
        connection_instance=capture.connection_instance,
        euid=capture.euid,
        pid=capture.pid,
        pidversion=capture.pidversion,
        plist_path="/Library/LaunchDaemons/com.mastermind.executive.control.plist",
        plist_uid=0,
        service_uid=capture.euid,
        argv=("/fixed/python", "-I", "-S", "-B", "/fixed/control.py"),
        python_provenance_digest="c" * 64,
        wrapper_digest="d" * 64,
        designated_requirement_digest="e" * 64,
        dynamic_code_identity_digest="f" * 64,
        dynamic_code_status=0,
    )


def bind_fixture(capture, observation=None):
    return peer._bind_qualified_owner_observation(
        peer._OWNER_CAPABILITY,
        peer=capture,
        observation=(
            observation if observation is not None else owner_observation(capture)
        ),
    )


def test_public_surface_remains_two_typed_apis():
    assert peer.__all__ == ["capture_peer_identity", "require_installed_service_peer"]
    assert not hasattr(peer.InstalledServicePeerBinding, "from_dict")
    assert not hasattr(peer.InstalledServicePeerBinding, "from_json")


@pytest.mark.parametrize(
    "kind", [peer.InstalledServicePeerBinding, peer.TrustedServicePeerContext]
)
def test_public_binding_and_context_constructors_refuse(kind):
    with pytest.raises(TypeError):
        kind()
    with pytest.raises(TypeError):
        kind(qualified=True, euid=501)


@pytest.mark.parametrize(
    "capability", [None, True, False, 0, {}, object(), "qualified"]
)
def test_data_cannot_supply_private_owner_capability(captured, capability):
    capture, _, _ = captured
    with pytest.raises(
        peer.PeerIdentityError, match="^SERVICE_OWNER_CAPABILITY_REQUIRED$"
    ):
        peer._bind_qualified_owner_observation(
            capability, peer=capture, observation=owner_observation(capture)
        )


@pytest.mark.parametrize(
    "binding", [None, True, {}, {"euid": 501, "qualified": True}, "root", 0]
)
def test_require_refuses_public_values_instead_of_binding(captured, binding):
    capture, _, _ = captured
    with pytest.raises(
        peer.PeerIdentityError, match="^SERVICE_OWNER_BINDING_REQUIRED$"
    ):
        peer.require_installed_service_peer(capture, binding)


def test_observation_or_structurally_forged_binding_is_not_authority(captured):
    capture, _, _ = captured
    for value in (
        owner_observation(capture),
        object.__new__(peer.InstalledServicePeerBinding),
    ):
        with pytest.raises(
            peer.PeerIdentityError, match="^SERVICE_OWNER_BINDING_REQUIRED$"
        ):
            peer.require_installed_service_peer(capture, value)


def test_owner_issued_binding_returns_exact_six_tuple(captured):
    capture, _, _ = captured
    observation = owner_observation(capture)
    binding = bind_fixture(capture, observation)
    result = peer.require_installed_service_peer(capture, binding)
    assert type(result) is peer.TrustedServicePeerContext
    assert tuple(result.__dataclass_fields__) == (
        "real_boot_id",
        "audit_identity_digest",
        "service_label",
        "installed_release",
        "config_digest",
        "connection_instance",
    )
    for name in result.__dataclass_fields__:
        assert getattr(result, name) == getattr(observation, name)
    assert result.connection_instance is capture.connection_instance
    with pytest.raises(AttributeError):
        result.config_digest = "0" * 64
    # Objects cannot become a serializable bearer credential.
    for value in (capture, binding, result):
        with pytest.raises(TypeError):
            copy.deepcopy(value)
        with pytest.raises(TypeError):
            pickle.loads(pickle.dumps(value))


def test_owner_input_is_snapshotted(captured):
    capture, _, _ = captured
    observation = owner_observation(capture)
    binding = bind_fixture(capture, observation)
    object.__setattr__(observation, "config_digest", "0" * 64)
    object.__setattr__(observation, "service_label", "different.service")
    result = peer.require_installed_service_peer(capture, binding)
    assert result.config_digest == "b" * 64
    assert result.service_label == "com.mastermind.executive.control"


@pytest.mark.parametrize("observation", [None, True, {}, {"qualified": True}])
def test_owner_observation_requires_exact_private_record(captured, observation):
    capture, _, _ = captured
    with pytest.raises(
        peer.PeerIdentityError, match="^SERVICE_OWNER_OBSERVATION_REQUIRED$"
    ):
        peer._bind_qualified_owner_observation(
            peer._OWNER_CAPABILITY, peer=capture, observation=observation
        )


@pytest.mark.parametrize(
    "name,value",
    [
        ("real_boot_id", ""),
        ("real_boot_id", None),
        ("real_boot_id", "00000000-0000-0000-0000-000000000000"),
        ("real_boot_id", "{11111111-1111-4111-8111-111111111111}"),
        ("audit_identity_digest", ""),
        ("config_digest", "b" * 63),
        ("python_provenance_digest", None),
        ("wrapper_digest", "G" * 64),
        ("designated_requirement_digest", True),
        ("dynamic_code_identity_digest", "F" * 64),
        ("installed_release", "main"),
        ("installed_release", "a" * 64),
        ("service_label", "system/com.mastermind.executive.control"),
        ("service_label", "x\n"),
        ("service_label", "x" * 161),
        ("plist_path", "relative/plist"),
        ("plist_path", "/path/../plist"),
        ("plist_path", "/path//plist"),
        ("plist_path", "/path/./plist"),
        ("plist_uid", 501),
        ("plist_uid", False),
        ("argv", ["/python"]),
        ("argv", ()),
        ("argv", ("python",)),
        ("argv", ("/python", "x\x00y")),
        ("argv", ("/python",) * 65),
        ("euid", True),
        ("service_uid", -1),
        ("pid", 0),
        ("pidversion", False),
    ],
)
def test_incomplete_or_malformed_owner_observations_refuse(captured, name, value):
    capture, _, _ = captured
    with pytest.raises(
        peer.PeerIdentityError, match="^SERVICE_OWNER_OBSERVATION_INVALID$"
    ):
        bind_fixture(capture, replace(owner_observation(capture), **{name: value}))


@pytest.mark.parametrize("status", [False, True, None, "0", 1, -67050])
def test_boolean_or_failed_dynamic_validation_is_not_success(captured, status):
    capture, _, _ = captured
    with pytest.raises(
        peer.PeerIdentityError, match="^SERVICE_DYNAMIC_CODE_NOT_VALID$"
    ):
        bind_fixture(
            capture, replace(owner_observation(capture), dynamic_code_status=status)
        )


@pytest.mark.parametrize(
    "name,value",
    [
        ("euid", 502),
        ("service_uid", 502),
        ("pid", 1235),
        ("pidversion", 5679),
        ("audit_identity_digest", "0" * 64),
        ("connection_instance", object()),
    ],
)
def test_same_uid_or_partial_identity_never_matches_full_peer(captured, name, value):
    capture, _, _ = captured
    with pytest.raises(
        peer.PeerIdentityError, match="^SERVICE_PEER_IDENTITY_MISMATCH$"
    ):
        bind_fixture(capture, replace(owner_observation(capture), **{name: value}))


def test_even_same_socket_recapture_requires_new_owner_binding(captured):
    capture, connection, _ = captured
    binding = bind_fixture(capture)
    again = peer.capture_peer_identity(connection)
    assert again.audit_identity_digest == capture.audit_identity_digest
    assert again.connection_instance is not capture.connection_instance
    with pytest.raises(peer.PeerIdentityError, match="^SERVICE_CONNECTION_MISMATCH$"):
        peer.require_installed_service_peer(again, binding)


@pytest.mark.parametrize(
    "name,value",
    [
        ("euid", 502),
        ("pid", 1235),
        ("pidversion", 5679),
        ("audit_token", b"J" * 32),
        ("descriptor_identity", (900, 901, 902, 903)),
    ],
)
def test_kernel_or_descriptor_drift_invalidates_previously_issued_binding(
    captured, monkeypatch, name, value
):
    capture, _, original = captured
    binding = bind_fixture(capture)
    monkeypatch.setattr(
        peer, "_observe_socket", lambda _: replace(original, **{name: value})
    )
    with pytest.raises(peer.PeerIdentityError, match="^PEER_IDENTITY_CHANGED$"):
        peer.require_installed_service_peer(capture, binding)


@pytest.mark.parametrize(
    "name,value",
    [
        ("euid", 0),
        ("pid", 1),
        ("pidversion", 1),
        ("audit_token", b"J" * 32),
        ("audit_identity_digest", "0" * 64),
        ("connection_instance", object()),
    ],
)
def test_public_field_tamper_refuses_before_owner_binding(captured, name, value):
    capture, _, _ = captured
    object.__setattr__(capture, name, value)
    with pytest.raises(peer.PeerIdentityError, match="^PEER_CAPTURE_ALTERED$"):
        bind_fixture(capture)


def test_receiver_process_change_refuses_inherited_capture(captured, monkeypatch):
    capture, _, _ = captured
    binding = bind_fixture(capture)
    original_pid = os.getpid()
    monkeypatch.setattr(peer.os, "getpid", lambda: original_pid + 1)
    with pytest.raises(peer.PeerIdentityError, match="^PEER_CAPTURE_PROCESS_CHANGED$"):
        peer.require_installed_service_peer(capture, binding)


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin kernel primitive")
def test_distinct_real_connections_with_same_peer_cannot_share_binding():
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    c, d = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        first = peer.capture_peer_identity(a)
        second = peer.capture_peer_identity(c)
        assert (first.euid, first.pid, first.pidversion) == (
            second.euid,
            second.pid,
            second.pidversion,
        )
        assert first.audit_identity_digest == second.audit_identity_digest
        binding = bind_fixture(first)
        with pytest.raises(
            peer.PeerIdentityError, match="^SERVICE_CONNECTION_MISMATCH$"
        ):
            peer.require_installed_service_peer(second, binding)
        assert (
            peer.require_installed_service_peer(first, binding).connection_instance
            is first.connection_instance
        )
        a.close()
        with pytest.raises(peer.PeerIdentityError):
            peer.require_installed_service_peer(first, binding)
    finally:
        for connection in (a, b, c, d):
            connection.close()


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin kernel primitive")
def test_capture_does_not_consume_or_trust_application_payload():
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        payload = b'{"euid":0,"pid":1,"qualified":true}'
        b.sendall(payload)
        captured = peer.capture_peer_identity(a)
        assert captured.euid == os.geteuid()
        assert captured.pid == os.getpid()
        assert a.recv(len(payload)) == payload
    finally:
        a.close()
        b.close()


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin kernel primitive")
def test_real_accepted_socket_binds_separate_process_not_receiver():
    # Short test-only socket pathname: macOS sockaddr_un has a small bound.
    child_code = (
        "import socket,sys; s=socket.socket(socket.AF_UNIX); "
        "s.connect(sys.argv[1]); "
        's.sendall(b\'{"euid":0,"pid":1,"qualified":true}\'); '
        "s.recv(1); s.close()"
    )
    with tempfile.TemporaryDirectory(prefix="p4peer-", dir="/private/tmp") as directory:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(directory + "/peer")
            server.listen(1)
            server.settimeout(5)
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    "-B",
                    "-c",
                    child_code,
                    directory + "/peer",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            try:
                connection, _ = server.accept()
                with connection:
                    connection.settimeout(5)
                    captured = peer.capture_peer_identity(connection)
                    assert captured.pid == process.pid
                    assert captured.pid != os.getpid()
                    assert captured.euid == os.geteuid()
                    assert captured.pidversion > 0
                    assert (
                        connection.recv(512) == b'{"euid":0,"pid":1,"qualified":true}'
                    )
                    binding = bind_fixture(captured)
                    context = peer.require_installed_service_peer(captured, binding)
                    assert (
                        context.audit_identity_digest == captured.audit_identity_digest
                    )
                    assert context.connection_instance is captured.connection_instance
                    connection.sendall(b"x")
                _, error = process.communicate(timeout=5)
                assert process.returncode == 0, error
                with pytest.raises(peer.PeerIdentityError):
                    peer.require_installed_service_peer(captured, binding)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=5)


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin kernel primitive")
def test_real_replaced_descriptor_refuses_even_with_same_peer_token():
    a, b = socket.socketpair()
    c, d = socket.socketpair()
    try:
        captured = peer.capture_peer_identity(a)
        binding = bind_fixture(captured)
        replacement = peer.capture_peer_identity(c)
        assert captured.audit_identity_digest == replacement.audit_identity_digest
        os.dup2(c.fileno(), a.fileno())
        with pytest.raises(peer.PeerIdentityError, match="^PEER_IDENTITY_CHANGED$"):
            peer.require_installed_service_peer(captured, binding)
    finally:
        for connection in (a, b, c, d):
            connection.close()


@pytest.mark.parametrize("missing", ["library", "symbol"])
def test_missing_bsm_api_fails_closed_without_fallback(monkeypatch, missing):
    monkeypatch.setattr(peer.sys, "platform", "darwin")

    def unavailable(_):
        if missing == "library":
            raise OSError("not installed")
        return object()

    monkeypatch.setattr(peer.ctypes, "CDLL", unavailable)
    with pytest.raises(peer.PeerIdentityError, match="^PEER_AUDIT_API_UNAVAILABLE$"):
        peer._darwin_accessors.__wrapped__()
