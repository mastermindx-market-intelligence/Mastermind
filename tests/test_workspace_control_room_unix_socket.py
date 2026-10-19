"""CRROOM-CORE: closed validator, peer gate, socket custody, lifecycle, and boot proof.

T1 - validate_workspace_control_room contract.
T2 - workspace_control_room_launchd_entry contract.
T3 - UnixControlRoomServer peer gate.
T4 - Socket custody invariants (closed reason codes).
T5 - HostedControlRoom over AF_UNIX.
T6 - Boot proof: zero TCP listeners and unchanged acceptance check.
T7 - Negative boot: Control owns a TCP listener -> acceptance refuses.
RC1 - Adoption closes the placeholder at the Python level (no leaked fd).
RC2 - verify_request catches every peer-uid error, server keeps serving.
RC3 - HostedControlRoom.start re-uses constructor-resolved custody values.
"""
from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import errno
import gc
import hashlib
import http.client
import json
import os
import shutil
import socket
import socketserver
import stat
import subprocess
import sys
import tempfile
import threading
import warnings
from pathlib import Path

import pytest

import control_plane.workspace_control_room_lifecycle as lifecycle_mod
from control_plane.executive_service import _peer_uid
from control_plane.workspace_control_room_lifecycle import (
    ControlRoomSocketRefused, HostedControlRoom, _verify_socket_custody,
)
from ops.executive_os import acceptance as acceptance_module
from scripts import executive_os_phase1c as cli
from scripts import chairman_control_room as ccr
from scripts.chairman_control_room import (
    UNIX_CONTROL_ROOM_HOST, UNIX_CONTROL_ROOM_ORIGIN,
)
from tests.executive_installed_control_fixture import (
    boot_installed_control, installed_control_config, unix_listener,
    UnixHTTPConnection, unix_stanza,
)
from tests.test_executive_fabric_composition import root_stats
from tests.test_fabric_attended_routing import router


# ---------------------------------------------------------------------------
# T1: validate_workspace_control_room
# ---------------------------------------------------------------------------


def _validation_failures():
    uid = os.geteuid()
    base = unix_stanza(uid)
    base.update(extras())
    yield ("extra_key", {**base, "extra": "x"}, "workspace Control Room topology refused")
    yield ("missing_key", {"transport": "unix",
                            "socket_path": cli._CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET,
                            "launchd_socket_name": cli._WORKSPACE_CONTROL_ROOM_SOCKET_NAME},
           "workspace Control Room topology refused")
    yield ("transport_tcp", {**base, "transport": "tcp"}, "workspace Control Room topology refused")
    yield ("wrong_socket_path", {**base, "socket_path": "/tmp/other.sock"},
           "workspace Control Room topology refused")
    yield ("wrong_launchd_name", {**base, "launchd_socket_name": "Other"},
           "workspace Control Room topology refused")
    yield ("empty_allowlist", {**base, "allowed_peer_uids": []},
           "workspace Control Room topology refused")
    yield ("duplicate_uid", {**base, "allowed_peer_uids": [uid, uid]},
           "workspace Control Room topology refused")
    yield ("bool_uid", {**base, "allowed_peer_uids": [True]},
           "workspace Control Room topology refused")
    yield ("stranger_uid", {**base, "allowed_peer_uids": [uid + 7]},
           "workspace Control Room topology refused")
    yield ("non_dict", [1, 2, 3], "workspace Control Room topology refused")
    yield ("none", None, "workspace Control Room topology refused")


def extras():
    return {}


def test_legacy_port_stanza_is_loudly_refused():
    with pytest.raises(cli.ServiceError, match="legacy TCP port stanza refused"):
        cli.validate_workspace_control_room({"port": 8787}, control_uid=os.geteuid())


def test_validation_rejects_invalid_shapes():
    uid = os.geteuid()
    for label, stanza, _message in _validation_failures():
        with pytest.raises(cli.ServiceError, match="workspace Control Room topology refused"):
            cli.validate_workspace_control_room(stanza, control_uid=uid)


def test_valid_stanza_returns_equal_copy():
    uid = os.geteuid()
    stanza = unix_stanza(uid)
    copy = cli.validate_workspace_control_room(stanza, control_uid=uid)
    assert copy == stanza
    assert copy is not stanza


# ---------------------------------------------------------------------------
# T2: workspace_control_room_launchd_entry
# ---------------------------------------------------------------------------


def test_launchd_entry_exact_dict_for_canonical_stanza():
    uid = os.geteuid()
    gid = os.getegid() if os.getegid() > 0 else 8000
    config = {"control_uid": uid, "workspace_control_room": unix_stanza(uid)}
    entry = cli.workspace_control_room_launchd_entry(config, control_gid=gid)
    assert entry == {
        "SockPathName": cli._CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET,
        "SockType": "stream", "SockPassive": True,
        "SockPathOwner": uid, "SockPathGroup": gid,
        "SockPathMode": 0o600,
    }
    assert entry["SockPathMode"] & 0o077 == 0
    assert entry["SockPathGroup"] == gid
    assert entry["SockPathGroup"] not in (470, 457, 458)


def test_launchd_entry_absent_stanza_returns_none():
    config = {"control_uid": os.geteuid()}
    assert cli.workspace_control_room_launchd_entry(config, control_gid=os.getegid()) is None


@pytest.mark.parametrize("bad_gid", [0, False, True, "0", -1])
def test_launchd_entry_rejects_bad_control_gid(bad_gid):
    uid = os.geteuid()
    config = {"control_uid": uid, "workspace_control_room": unix_stanza(uid)}
    with pytest.raises(cli.ServiceError):
        cli.workspace_control_room_launchd_entry(config, control_gid=bad_gid)


# ---------------------------------------------------------------------------
# T3: peer gate
# ---------------------------------------------------------------------------


def _spawn_unix_server(allowed_peer_uids, peer_uid_fn):
    """Spawn a real UnixControlRoomServer thread for the gate tests."""

    config = ccr.ServerConfig(repo_root=Path("/tmp"), macro_root=None, bindings_path=None,
        token="fixture", origin=UNIX_CONTROL_ROOM_ORIGIN, port=0, state_ttl=10.0)
    listener, path = unix_listener()
    server = ccr.UnixControlRoomServer(listener, ccr.ChairmanControlRoomHandler, config,
        allowed_peer_uids=frozenset(allowed_peer_uids), peer_uid_fn=peer_uid_fn)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    return server, thread, path


def _stop_server(server, thread):
    try:
        server.shutdown()
    finally:
        server.server_close()
        thread.join(timeout=2.0)


def test_peer_gate_refuses_non_allowlisted_uid():
    """peer_uid_fn returns geteuid()+1 but allowlist is [geteuid()]."""
    server, thread, path = _spawn_unix_server(
        [os.geteuid()], lambda _conn: os.geteuid() + 1)
    try:
        conn = UnixHTTPConnection(path)
        try:
            with pytest.raises((ConnectionResetError, BrokenPipeError, OSError)):
                conn.request("GET", "/", headers={"Host": UNIX_CONTROL_ROOM_HOST})
                conn.getresponse()
        finally:
            conn.close()
    finally:
        _stop_server(server, thread)


def test_peer_gate_refuses_none_uid():
    server, thread, path = _spawn_unix_server([os.geteuid()], lambda _conn: None)
    try:
        conn = UnixHTTPConnection(path)
        try:
            with pytest.raises((ConnectionResetError, BrokenPipeError, OSError)):
                conn.request("GET", "/", headers={"Host": UNIX_CONTROL_ROOM_HOST})
                conn.getresponse()
        finally:
            conn.close()
    finally:
        _stop_server(server, thread)


def test_peer_gate_refuses_oserror_uid():
    def raise_oserror(_conn):
        raise OSError(errno.EACCES, "no creds")
    server, thread, path = _spawn_unix_server([os.geteuid()], raise_oserror)
    try:
        conn = UnixHTTPConnection(path)
        try:
            with pytest.raises((ConnectionResetError, BrokenPipeError, OSError)):
                conn.request("GET", "/", headers={"Host": UNIX_CONTROL_ROOM_HOST})
                conn.getresponse()
        finally:
            conn.close()
    finally:
        _stop_server(server, thread)


def test_peer_gate_admits_allowlisted_uid_with_expected_host():
    server, thread, path = _spawn_unix_server(
        [os.geteuid()], _peer_uid)
    try:
        conn = UnixHTTPConnection(path)
        try:
            conn.request("GET", "/api/state", headers={
                "Host": UNIX_CONTROL_ROOM_HOST,
                "Origin": UNIX_CONTROL_ROOM_ORIGIN,
                "X-CCR-Token": "fixture",
            })
            resp = conn.getresponse()
            assert resp.status == 200
        finally:
            conn.close()
    finally:
        _stop_server(server, thread)


def test_peer_gate_refuses_uid_not_in_allowlist_with_real_peer_uid():
    server, thread, path = _spawn_unix_server(
        [os.geteuid() + 1], _peer_uid)
    try:
        conn = UnixHTTPConnection(path)
        try:
            with pytest.raises((ConnectionResetError, BrokenPipeError, OSError)):
                conn.request("GET", "/", headers={"Host": UNIX_CONTROL_ROOM_HOST})
                conn.getresponse()
        finally:
            conn.close()
    finally:
        _stop_server(server, thread)


def test_host_header_loopback_refused_for_unix_peer():
    server, thread, path = _spawn_unix_server([os.geteuid()], _peer_uid)
    try:
        conn = UnixHTTPConnection(path)
        try:
            conn.request("GET", "/", headers={"Host": "127.0.0.1"})
            resp = conn.getresponse()
            assert resp.status == 403
            body = resp.read().decode("utf-8")
            assert "Host header not allowed" in body
        finally:
            conn.close()
    finally:
        _stop_server(server, thread)


# ---------------------------------------------------------------------------
# T4: custody
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_unix_sock():
    listener, path = unix_listener()
    try:
        yield listener, path
    finally:
        listener.close()
        try:
            os.unlink(path)
        except OSError:
            pass


def test_custody_default_allowlist_succeeds(tmp_path, tmp_unix_sock, monkeypatch):
    listener, path = tmp_unix_sock
    monkeypatch.setattr(lifecycle_mod, "_TRUSTED_SOCKET_PARENT_UID", os.geteuid())
    _verify_socket_custody(listener, socket_path=path,
                            expected_owner_uid=os.geteuid(),
                            expected_gid=os.getegid(),
                            trusted_parent_uid=os.geteuid())


@pytest.mark.parametrize("bad_mode", [0o666, 0o660, 0o644, 0o700])
def test_custody_mode_refused(tmp_path, tmp_unix_sock, monkeypatch, bad_mode):
    listener, path = tmp_unix_sock
    monkeypatch.setattr(lifecycle_mod, "_TRUSTED_SOCKET_PARENT_UID", os.geteuid())
    os.chmod(path, bad_mode)
    with pytest.raises(ControlRoomSocketRefused) as info:
        _verify_socket_custody(listener, socket_path=path,
                                expected_owner_uid=os.geteuid(),
                                expected_gid=os.getegid(),
                                trusted_parent_uid=os.geteuid())
    assert "mode" in str(info.value)


def test_custody_owner_refused(tmp_path, tmp_unix_sock, monkeypatch):
    listener, path = tmp_unix_sock
    monkeypatch.setattr(lifecycle_mod, "_TRUSTED_SOCKET_PARENT_UID", os.geteuid())
    with pytest.raises(ControlRoomSocketRefused) as info:
        _verify_socket_custody(listener, socket_path=path,
                                expected_owner_uid=os.geteuid() + 1,
                                expected_gid=os.getegid(),
                                trusted_parent_uid=os.geteuid())
    assert "owner" in str(info.value)


def test_custody_group_refused(tmp_path, tmp_unix_sock, monkeypatch):
    listener, path = tmp_unix_sock
    monkeypatch.setattr(lifecycle_mod, "_TRUSTED_SOCKET_PARENT_UID", os.geteuid())
    with pytest.raises(ControlRoomSocketRefused) as info:
        _verify_socket_custody(listener, socket_path=path,
                                expected_owner_uid=os.geteuid(),
                                expected_gid=os.getegid() + 1,
                                trusted_parent_uid=os.geteuid())
    assert "group" in str(info.value)


def test_custody_symlink_refused(tmp_path, tmp_unix_sock, monkeypatch):
    listener, path = tmp_unix_sock
    monkeypatch.setattr(lifecycle_mod, "_TRUSTED_SOCKET_PARENT_UID", os.geteuid())
    # The listener holds the original inode via its open fd. Replace the
    # file at ``path`` with a symlink at the same name pointing elsewhere:
    # the path-mismatch check sees matching basenames and falls through to
    # the lstat step, which observes S_IFLNK.
    listener_fd_was = listener.fileno()
    # Build a real socket file elsewhere, then swap.
    other_dir = tempfile.mkdtemp(prefix="crr", dir="/tmp")
    target = os.path.join(other_dir, "target.sock")
    target_listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    target_listener.bind(target)
    os.chmod(target, 0o600)
    target_listener.close()
    os.unlink(path)
    os.symlink(target, path)
    try:
        with pytest.raises(ControlRoomSocketRefused) as info:
            _verify_socket_custody(listener, socket_path=path,
                                    expected_owner_uid=os.geteuid(),
                                    expected_gid=os.getegid(),
                                    trusted_parent_uid=os.geteuid())
        assert "symlink" in str(info.value)
    finally:
        os.unlink(path)
        listener.close()
        try:
            os.unlink(target)
        except OSError:
            pass


def test_custody_parent_writable_refused(tmp_path, tmp_unix_sock, monkeypatch):
    listener, path = tmp_unix_sock
    monkeypatch.setattr(lifecycle_mod, "_TRUSTED_SOCKET_PARENT_UID", os.geteuid())
    parent = os.path.dirname(path)
    os.chmod(parent, 0o777)
    try:
        with pytest.raises(ControlRoomSocketRefused) as info:
            _verify_socket_custody(listener, socket_path=path,
                                    expected_owner_uid=os.geteuid(),
                                    expected_gid=os.getegid(),
                                    trusted_parent_uid=os.geteuid())
        assert "parent-writable" in str(info.value)
    finally:
        os.chmod(parent, 0o700)


def test_custody_parent_owner_refused_with_default_seam(tmp_path, tmp_unix_sock):
    listener, path = tmp_unix_sock
    parent = os.path.dirname(path)
    if os.geteuid() == 0:
        # Running as root: chown the parent to uid 1 (keep gid) so the
        # default trusted-parent seam (uid 0) always refuses with "parent-owner".
        os.chown(parent, 1, -1)
    with pytest.raises(ControlRoomSocketRefused) as info:
        _verify_socket_custody(listener, socket_path=path,
                                expected_owner_uid=os.geteuid(),
                                expected_gid=os.getegid(),
                                trusted_parent_uid=0)
    assert "parent-owner" in str(info.value)


def test_custody_not_unix_stream_refused(tmp_path):
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.bind(("127.0.0.1", 0))
    tcp.listen(1)
    try:
        with pytest.raises(ControlRoomSocketRefused) as info:
            _verify_socket_custody(tcp, socket_path="/tmp/whatever",
                                    expected_owner_uid=os.geteuid(),
                                    expected_gid=os.getegid(),
                                    trusted_parent_uid=os.geteuid())
        assert "not-unix-stream" in str(info.value)
    finally:
        tcp.close()


def test_custody_path_mismatch_refused(tmp_path, tmp_unix_sock, monkeypatch):
    listener, path = tmp_unix_sock
    monkeypatch.setattr(lifecycle_mod, "_TRUSTED_SOCKET_PARENT_UID", os.geteuid())
    # A second AF_UNIX listener on a different path.
    other_listener, other_path = unix_listener()
    try:
        with pytest.raises(ControlRoomSocketRefused) as info:
            _verify_socket_custody(other_listener, socket_path=path,
                                    expected_owner_uid=os.geteuid(),
                                    expected_gid=os.getegid(),
                                    trusted_parent_uid=os.geteuid())
        assert "path-mismatch" in str(info.value)
    finally:
        other_listener.close()
        try:
            os.unlink(other_path)
        except OSError:
            pass


def test_custody_not_socket_refused(tmp_path, tmp_unix_sock, monkeypatch):
    listener, path = tmp_unix_sock
    monkeypatch.setattr(lifecycle_mod, "_TRUSTED_SOCKET_PARENT_UID", os.geteuid())
    regular = path + ".regular"
    with open(regular, "w") as f:
        f.write("not a socket")
    os.chmod(regular, 0o600)
    # Wrap the AF_UNIX listener with an adapter whose getsockname() returns
    # the regular file's path; the path-mismatch invariant is exercised by
    # its own dedicated test.
    class _Adapter:
        family = socket.AF_UNIX
        type = socket.SOCK_STREAM
        def __init__(self, inner, name):
            self._inner = inner
            self._name = name
        def getsockname(self):
            return self._name
        def getsockopt(self, level, optname, *args):
            return self._inner.getsockopt(level, optname, *args)
        def fileno(self):
            return self._inner.fileno()
    adapter = _Adapter(listener, regular)
    with pytest.raises(ControlRoomSocketRefused) as info:
        _verify_socket_custody(adapter, socket_path=regular,
                                expected_owner_uid=os.geteuid(),
                                expected_gid=os.getegid(),
                                trusted_parent_uid=os.geteuid())
    assert "not-socket" in str(info.value)
    os.unlink(regular)


# ---------------------------------------------------------------------------
# T5: lifecycle
# ---------------------------------------------------------------------------


def test_unix_lifecycle_start_close_thread_names(tmp_path, monkeypatch):
    monkeypatch.setattr(ccr, "_compose_state_doc", lambda *a, **k: {"schema": "x",
        "generated_at": "2026-09-21T00:00:00Z", "work": [],
        "autonomy": {"generated_at": "2026-09-21T00:00:00Z", "responsibilities": []}})
    monkeypatch.setattr(ccr.capability, "census", lambda **kwargs: {})
    monkeypatch.setattr(lifecycle_mod, "_TRUSTED_SOCKET_PARENT_UID", os.geteuid())
    listener, path = unix_listener()
    try:
        config = ccr.ServerConfig(repo_root=tmp_path, macro_root=None, bindings_path=None,
            token="fixture", origin=UNIX_CONTROL_ROOM_ORIGIN, port=0, state_ttl=10.0)
        host = HostedControlRoom(config, listener=listener, socket_path=path,
                                 allowed_peer_uids=(os.geteuid(),))

        async def run():
            await host.start()
            try:
                names = {t.name for t in threading.enumerate()}
                assert "workspace-canonical-control-room" in names
                assert "workspace-control-room-refresh" in names
                fd = host._listener.fileno()
                # The unix listener fd must stay open while serving.
                assert host._listener.fileno() >= 0
                # Sanity: HTTP over the socket returns 200.
                await asyncio.to_thread(lambda: _http_get(path, "/api/state"))
            finally:
                await host.close()
            names = {t.name for t in threading.enumerate()}
            assert "workspace-canonical-control-room" not in names
            assert "workspace-control-room-refresh" not in names
            assert host._listener.fileno() == -1

        asyncio.run(run())
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _http_get(path, url):
    conn = UnixHTTPConnection(path)
    try:
        conn.request("GET", url, headers={
            "Host": UNIX_CONTROL_ROOM_HOST,
            "Origin": UNIX_CONTROL_ROOM_ORIGIN,
            "X-CCR-Token": "fixture",
        })
        return conn.getresponse().read()
    finally:
        conn.close()


def test_hosted_control_room_class_identity_kept(tmp_path):
    # workspace_read_service requires `type(control_room) is HostedControlRoom`,
    # so the class identity must not change.
    assert HostedControlRoom.__name__ == "HostedControlRoom"
    # The factory imports HostedControlRoom lazily and runs `type(...) is`
    # on the exact class object; the symbol resolves to the same module.
    import control_plane.workspace_read_service as wsr
    import inspect
    src = inspect.getsource(wsr.workspace_provider_factory)
    assert "from control_plane.workspace_control_room_lifecycle import HostedControlRoom" in src
    assert "type(control_room) is not HostedControlRoom" in src


# ---------------------------------------------------------------------------
# RC1: adopted-socket adoption must not leak a placeholder fd
# ---------------------------------------------------------------------------


def test_unix_server_adoption_leaves_no_unclosed_placeholder():
    """Constructing UnixControlRoomServer over an adopted listener must close
    the placeholder UnixStreamServer socket at the Python level, not by raw
    os.close(fileno()) — a raw close leaves the Python socket object alive,
    its finalizer later closes the same descriptor number, and that can land
    on an unrelated file the kernel has handed to another thread.
    """

    config = ccr.ServerConfig(repo_root=Path("/tmp"), macro_root=None, bindings_path=None,
        token="fixture", origin=UNIX_CONTROL_ROOM_ORIGIN, port=0, state_ttl=10.0)
    listener, path = unix_listener()
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", ResourceWarning)
        try:
            server = ccr.UnixControlRoomServer(
                listener, ccr.ChairmanControlRoomHandler, config,
                allowed_peer_uids=frozenset({os.geteuid()}), peer_uid_fn=_peer_uid)
        finally:
            gc.collect()
    offenders = [str(w.message) for w in captured if "unclosed" in str(w.message).lower()]
    assert offenders == [], f"ResourceWarning leaked: {offenders}"
    # The adopted listener IS the server's socket object.
    assert server.socket is listener
    # The adopted fd is still live and valid.
    os.fstat(listener.fileno())
    server.server_close()
    assert listener.fileno() == -1
    try:
        os.unlink(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# RC2: verify_request must refuse AND keep the server alive on unexpected errors
# ---------------------------------------------------------------------------


def test_peer_uid_unexpected_error_refuses_and_server_keeps_serving():
    """An unexpected (non-OSError) exception from peer_uid_fn must close the
    connection without ever invoking the handler, and must NOT escape into
    serve_forever — a second connection from an allowlisted peer then gets
    HTTP 200 from the SAME live server thread.
    """

    config = ccr.ServerConfig(repo_root=Path("/tmp"), macro_root=None, bindings_path=None,
        token="fixture", origin=UNIX_CONTROL_ROOM_ORIGIN, port=0, state_ttl=10.0)
    listener, path = unix_listener()
    handler_calls: list[None] = []

    class _SpyHandler(ccr.ChairmanControlRoomHandler):
        def handle(self):  # type: ignore[override]
            handler_calls.append(None)
            return super().handle()

    state = {"calls": 0}

    def peer_uid_fn(_conn):
        state["calls"] += 1
        if state["calls"] == 1:
            raise ValueError("simulated peer-credential failure")
        return _peer_uid(_conn)

    server = ccr.UnixControlRoomServer(
        listener, _SpyHandler, config,
        allowed_peer_uids=frozenset({os.geteuid()}), peer_uid_fn=peer_uid_fn)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        # 1) The first connection is refused: no HTTP response bytes at all.
        bad = UnixHTTPConnection(path)
        try:
            with pytest.raises((ConnectionResetError, BrokenPipeError, OSError)):
                bad.request("GET", "/", headers={"Host": UNIX_CONTROL_ROOM_HOST})
                bad.getresponse()
        finally:
            bad.close()
        assert handler_calls == [], "handler must never be invoked on a refused peer"
        assert thread.is_alive(), "server thread must keep serving after the first refusal"
        # 2) A second connection from an allowlisted peer is admitted.
        good = UnixHTTPConnection(path)
        try:
            good.request("GET", "/api/state", headers={
                "Host": UNIX_CONTROL_ROOM_HOST,
                "Origin": UNIX_CONTROL_ROOM_ORIGIN,
                "X-CCR-Token": "fixture",
            })
            resp = good.getresponse()
            assert resp.status == 200
            assert resp.read()  # body delivered
        finally:
            good.close()
        assert thread.is_alive(), "server thread must still be alive after a 200"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)
        try:
            os.unlink(path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# RC3: HostedControlRoom.start re-uses constructor-resolved custody values
# ---------------------------------------------------------------------------


def test_start_recheck_uses_constructor_custody_values(tmp_path, monkeypatch):
    """If the constructor resolved expected_owner_uid / expected_gid, the
    _start re-check MUST use those exact values — not the live geteuid /
    getegid (which may have been mutated by a setuid wrapper or a test
    monkeypatch). T4 above proves the same identity still refuses when the
    constructor DID NOT receive explicit values and the live identity has
    mutated.
    """

    # Avoid the durable precompose side-effect in production: stub it.
    monkeypatch.setattr(ccr, "_compose_state_doc", lambda *a, **k: {"schema": "x",
        "generated_at": "2026-09-21T00:00:00Z", "work": [],
        "autonomy": {"generated_at": "2026-09-21T00:00:00Z", "responsibilities": []}})
    monkeypatch.setattr(ccr.capability, "census", lambda **kwargs: {})
    monkeypatch.setattr(lifecycle_mod, "_TRUSTED_SOCKET_PARENT_UID", os.geteuid())

    listener, path = unix_listener()
    config = ccr.ServerConfig(repo_root=tmp_path, macro_root=None, bindings_path=None,
        token="fixture", origin=UNIX_CONTROL_ROOM_ORIGIN, port=0, state_ttl=10.0)

    # Constructor receives the REAL identity, which passes the verification.
    real_uid = os.geteuid()
    real_gid = os.getegid()
    host = HostedControlRoom(config, listener=listener, socket_path=path,
                             allowed_peer_uids=(real_uid,),
                             expected_owner_uid=real_uid,
                             expected_gid=real_gid)

    # Now mutate the live identity in the lifecycle module so the re-check
    # would only pass if it used the constructor values, not os.geteuid.
    monkeypatch.setattr(lifecycle_mod.os, "geteuid", lambda: real_uid + 1)
    monkeypatch.setattr(lifecycle_mod.os, "getegid", lambda: real_gid + 1)

    # The re-check uses the constructor values, so start() must succeed.
    asyncio.run(host.start())
    try:
        assert host._listener.fileno() >= 0
    finally:
        asyncio.run(host.close())
    try:
        os.unlink(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# T6 / T7: installed boot proof and negative boot
# ---------------------------------------------------------------------------


# Module-level flag: audit hooks cannot be removed once installed, so the
# installed hook short-circuits itself outside the T6/T7 window. The flag is
# only ever True inside the boot tests.
_AUDIT_HOOK_ACTIVE: bool = False
_AUDIT_HOOK_SEEN: list[tuple[str, object]] = []


def _audit_hook(event, args):
    """Audit-hook recording.

    For ``socket.__new__`` the socket object is not initialised, so ``family``
    must be read from ``args[1]`` (the family argument). For ``socket.bind``
    the socket IS initialised and ``args[0].family`` is the right source.
    T7 deliberately opens a TCP socket so the recording contains that bind
    event — an empty list at the end of T6 is only meaningful because T7 proves
    the hook is live.
    """
    if not _AUDIT_HOOK_ACTIVE:
        return
    if event == "socket.__new__":
        # args = (socket_cls, family, type, proto, fileno)
        if len(args) >= 2 and args[1] in (socket.AF_INET, socket.AF_INET6):
            _AUDIT_HOOK_SEEN.append((event, args[1]))
        return
    if event == "socket.bind":
        sock = args[0] if args else None
        family = getattr(sock, "family", None)
        if family in (socket.AF_INET, socket.AF_INET6):
            _AUDIT_HOOK_SEEN.append((event, getattr(sock, "type", "?")))
        return


sys.addaudithook(_audit_hook)


class _SocketLike:
    def is_socket(self):
        return True


def _read_proc_listening_inodes():
    """Return the inode set of TCP sockets in state 0A that belong to /proc/self/fd."""

    inodes = set()
    try:
        for entry in os.listdir("/proc/self/fd"):
            try:
                target = os.readlink(os.path.join("/proc/self/fd", entry))
            except OSError:
                continue
            if target.startswith("socket:["):
                try:
                    inodes.add(int(target[len("socket:["):-1]))
                except ValueError:
                    pass
    except OSError:
        return set()
    listening = set()
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            text = Path(path).read_text()
        except OSError:
            continue
        for line in text.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 10:
                continue
            if parts[3] != "0A":
                continue
            inode = int(parts[9])
            if inode in inodes:
                listening.add(inode)
    return listening


def _install_lsof_rewriter(monkeypatch):
    """Install the acceptance-module lsof rewriter used by both T6 and T7.

    The production code at ``ops/executive_os/acceptance.py`` calls
    ``subprocess.run(["/usr/sbin/lsof", "-u", <account>, "-nP", "-a", "-iTCP",
    "-sTCP:LISTEN"])``. On a CI host the fixed lsof path may not exist and
    ``-u <account>`` may not match the current account; we replace argv[0]
    with the host-resolved lsof binary and swap ``-u <account>`` for
    ``-w -p <pid>`` so the query is local and complete. The remaining flags
    (``-nP -a -iTCP -sTCP:LISTEN``) are preserved verbatim so the listener
    scan still restricts to listening TCP sockets only — never rewriting the
    production contract. Returns nothing; raises pytest.fail if lsof is missing.
    """

    lsof_path = shutil.which("lsof")
    if lsof_path is None:
        pytest.fail("lsof unavailable; install lsof for the acceptance checker")
    original_run = acceptance_module._run

    def rewriter(argv, **kwargs):
        rewritten = [lsof_path]
        skip_next = False
        for token in argv[1:]:
            if skip_next:
                skip_next = False
                continue
            if token == "-u":
                skip_next = True
                rewritten.extend(["-w", "-p", str(os.getpid())])
                continue
            rewritten.append(token)
        return original_run(rewritten, **kwargs)

    monkeypatch.setattr(acceptance_module, "_run", rewriter)
    monkeypatch.setattr(acceptance_module, "CONTROL_SOCKET", _SocketLike())
    monkeypatch.setattr(acceptance_module, "WORKER_SOCKET", _SocketLike())


def _http_get_over_unix(socket_path, url, host_header):
    """Synchronous GET over the AF_UNIX socket; returns the response body."""

    conn = UnixHTTPConnection(socket_path)
    try:
        conn.request("GET", url, headers={"Host": host_header})
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


def test_installed_boot_proves_zero_tcp_listeners(tmp_path, monkeypatch, root_stats, router):
    """Drive the REAL ``_serve_from_config`` -> ``load_control_config`` ->
    ``_service_from_config`` and prove the production room binds no TCP
    listener. The finite, dialogue Wake, and workspace stanzas are LIVE.

    While the production room serves we assert, in order:
      1. the audit hook recording holds no AF_INET / AF_INET6 event;
      2. on Linux, no inode of this process's socket fds appears in
         ``/proc/net/tcp`` or ``/proc/net/tcp6`` with state ``0A`` (on
         non-Linux we assert the lsof step below instead; never skip);
      3. the UNCHANGED ``object.__new__(acceptance.Acceptance)._assert_no_public_listener()``
         passes with the same r3 rewriter (argv[0] -> shutil.which("lsof"),
         "-u <account>" -> "-w -p <pid>"; ``pytest.fail("lsof unavailable")``
         if lsof is missing) and ``CONTROL_SOCKET`` / ``WORKER_SOCKET`` patched
         to ``is_socket()``-True objects;
      4. a real HTTP ``GET /`` over the room socket with
         ``Host workspace-control-room.invalid`` returns 200.

    After the boot we assert: ``WorkspaceControlRoom`` is in the requested
    launchd names; ``proof.room.config.port == 0``; ``proof.room.config.origin ==
    UNIX_CONTROL_ROOM_ORIGIN``; ``proof.room.allowed_peer_uids == (raw
    control_uid,)``; the room's listener family is AF_UNIX; after close the
    room listener's fileno() is ``-1`` or the room refuses reuse.
    """

    proof = zero_tcp_boot(tmp_path, monkeypatch, root_stats, router)
    control_uid = os.geteuid()

    # Post-boot invariants: the boot reached the production room construction.
    assert "WorkspaceControlRoom" in proof.requested_names
    assert proof.room.config.port == 0
    assert proof.room.config.origin == UNIX_CONTROL_ROOM_ORIGIN
    assert proof.room.allowed_peer_uids == (control_uid,)
    assert proof.room._listener.family == socket.AF_UNIX
    # The capture class already closed the room; the listener fd must be retired.
    assert proof.room._listener.fileno() == -1
    # Reuse is refused.
    with pytest.raises(ValueError):
        asyncio.run(proof.room.start())


def zero_tcp_boot(tmp_path, monkeypatch, root_stats, router, *, transform=None):
    """Boot the installed composition through the REAL loader and REAL
    composition and prove zero TCP listeners. Extracted from
    ``test_installed_boot_proves_zero_tcp_listeners`` so other tests can drive
    the same audit-hook window, lsof rewriter, and ``during_serve`` invariants.
    A ``transform`` (applied to the composed ``raw`` dict immediately before
    writing) lets a caller inject a finite-staging candidate into the same
    boot. Returns the ``BootProof``; the caller performs any post-boot invariants.
    """

    _ = root_stats
    _ = router

    global _AUDIT_HOOK_ACTIVE, _AUDIT_HOOK_SEEN
    _AUDIT_HOOK_SEEN = []
    _AUDIT_HOOK_ACTIVE = True
    _install_lsof_rewriter(monkeypatch)

    served = {}
    control_uid = os.geteuid()

    async def during_serve(room):
        # 4. HTTP GET / over AF_UNIX with the workspace Host header.
        status, body = await asyncio.to_thread(
            _http_get_over_unix,
            room.socket_path,
            "/",
            "workspace-control-room.invalid",
        )
        assert status == 200, f"expected 200, got {status}"
        assert body, "expected non-empty body from production room"
        # 1. Audit hook saw no AF_INET / AF_INET6 bind events.
        assert _AUDIT_HOOK_SEEN == [], (
            f"unexpected AF_INET/AF_INET6 bind events: {_AUDIT_HOOK_SEEN}")
        # 2. /proc/net/tcp{,6} holds no listening socket of this process.
        if sys.platform.startswith("linux"):
            assert _read_proc_listening_inodes() == set(), (
                "process owns a TCP socket in state LISTEN")
        # 3. The unchanged acceptance check accepts the boot.
        instance = object.__new__(acceptance_module.Acceptance)
        instance._assert_no_public_listener()
        served["room"] = room

    try:
        proof = boot_installed_control(
            tmp_path, monkeypatch, root_stats, router,
            during_serve=during_serve, transform=transform)
    finally:
        _AUDIT_HOOK_ACTIVE = False

    return proof


@pytest.mark.parametrize("bind_host,bind_family", [
    ("127.0.0.1", socket.AF_INET),
    ("0.0.0.0", socket.AF_INET),
    ("::", socket.AF_INET6),
])
def test_installed_boot_refuses_owning_a_tcp_listener(
        tmp_path, monkeypatch, root_stats, router, bind_host, bind_family):
    """Drive the REAL boot with a deliberate TCP listener and prove the
    audit hook is live AND the unchanged acceptance check refuses.

    Three parameter cases cover AF_INET on loopback, AF_INET on wildcard,
    and AF_INET6 on wildcard. T7 is the discriminating negative that proves
    T6's audit hook (empty recording in T6) is live: the deliberate TCP
    bind must appear in the hook's recording.
    """

    global _AUDIT_HOOK_ACTIVE, _AUDIT_HOOK_SEEN
    _AUDIT_HOOK_SEEN = []
    _AUDIT_HOOK_ACTIVE = True
    _install_lsof_rewriter(monkeypatch)

    tcp_socket = socket.socket(bind_family, socket.SOCK_STREAM)
    tcp_socket.bind((bind_host, 0))
    tcp_socket.listen(1)
    try:
        async def during_serve(room):
            # The TCP listener is already bound and listening. The hook
            # must have recorded the deliberate family; that proves the
            # hook is live (T6's empty recording is only meaningful
            # because T7 proves the hook is live).
            matching = [(event, value) for (event, value) in _AUDIT_HOOK_SEEN
                        if event == "socket.__new__" and value == bind_family]
            assert matching, (
                f"audit hook did not record the deliberate "
                f"socket.__new__ for family {bind_family}; "
                f"events: {_AUDIT_HOOK_SEEN}")
            instance = object.__new__(acceptance_module.Acceptance)
            with pytest.raises(acceptance_module.AcceptanceError,
                               match="owns a TCP listener"):
                instance._assert_no_public_listener()

        try:
            proof = boot_installed_control(
                tmp_path, monkeypatch, root_stats, router,
                during_serve=during_serve)
        finally:
            _AUDIT_HOOK_ACTIVE = False
        assert proof.room._listener.family == socket.AF_UNIX
    finally:
        try:
            tcp_socket.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Gate: UnixControlRoomServer refuses a listener that is not AF_UNIX / SOCK_STREAM
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", ["tcp", "dgram"])
def test_unix_server_class_refuses_non_unix_stream_listener(tmp_path, case):
    """UnixControlRoomServer.__init__ MUST reject a listener whose family
    is not AF_UNIX or whose type is not SOCK_STREAM. Otherwise disabling the
    constructor's gate (e.g. ``if False and (...)``) would let the class
    serve HTTP over a TCP listener, undermining the closed unix-peer model.

    Two cases:
      1. AF_INET SOCK_STREAM socket bound to ("127.0.0.1", 0) and listening.
      2. AF_UNIX SOCK_DGRAM socket bound to a path under tmp_path.

    Reuses the handler class and config object the file's existing
    UnixControlRoomServer tests use (ChairmanControlRoomHandler and the
    ServerConfig constructed in _spawn_unix_server).
    """
    if case == "tcp":
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
    else:
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        listener.bind(os.fspath(tmp_path / "dgram.sock"))
    try:
        config = ccr.ServerConfig(
            repo_root=Path("/tmp"), macro_root=None, bindings_path=None,
            token="fixture", origin=UNIX_CONTROL_ROOM_ORIGIN, port=0, state_ttl=10.0,
        )
        with pytest.raises(ValueError, match="control room unix listener refused"):
            ccr.UnixControlRoomServer(
                listener, ccr.ChairmanControlRoomHandler, config,
                allowed_peer_uids=frozenset({os.getuid()}),
                peer_uid_fn=_peer_uid,
            )
    finally:
        listener.close()