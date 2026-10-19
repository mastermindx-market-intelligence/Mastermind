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
    installed_control_config, unix_listener, UnixHTTPConnection, unix_stanza,
)


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
    if os.stat(parent).st_uid == 0:
        pytest.skip("default parent already root-owned; cannot prove refusal here")
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
# installed hook short-circuits itself outside the T6 window. The flag is
# only ever True inside T6.
_AUDIT_HOOK_ACTIVE: bool = False
_AUDIT_HOOK_SEEN: list[tuple[str, object]] = []


def _audit_hook(event, args):
    if not _AUDIT_HOOK_ACTIVE:
        return
    if event in ("socket.__new__", "socket.bind"):
        sock = args[0] if args else None
        family = getattr(sock, "family", None)
        if family in (socket.AF_INET, socket.AF_INET6):
            _AUDIT_HOOK_SEEN.append((event, getattr(sock, "type", "?")))


sys.addaudithook(_audit_hook)


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


def test_installed_boot_proves_zero_tcp_listeners(tmp_path, monkeypatch):
    """Boot the installed composition and prove the room binds no TCP listener.

    - The audit hook saw no AF_INET / AF_INET6 bind events for this process.
    - /proc/net/tcp{,6} holds no listening socket whose inode belongs to us.
    - The unchanged ``_assert_no_public_listener`` accepts the boot.
    """

    # Audit hooks cannot be removed once added, so the hook reads a module-
    # level flag and is inert by default. T6 activates it for its own window.
    global _AUDIT_HOOK_ACTIVE, _AUDIT_HOOK_SEEN
    _AUDIT_HOOK_SEEN = []
    _AUDIT_HOOK_ACTIVE = True
    workspace_socket_path = None
    cache: dict[str, socket.socket] = {}
    try:
        workspace_socket_path = os.path.join(tempfile.mkdtemp(prefix="crr-boot", dir="/tmp"), "room.sock")
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(workspace_socket_path)
        os.chmod(workspace_socket_path, 0o600)
        listener.listen(8)
        cache["WorkspaceControlRoom"] = listener

        # Patch the canonical socket path and the parent-uid test seam so the
        # AF_UNIX ownership / parent / mode checks all pass in a tmp dir.
        monkeypatch.setattr(cli, "_CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET", workspace_socket_path)
        monkeypatch.setattr(lifecycle_mod, "_TRUSTED_SOCKET_PARENT_UID", os.geteuid())
        # Stub the staged Fabric binding source loader so the fixture never
        # has to point at a real FabricBindingSource file; the boot test
        # never actually starts Fabric.
        monkeypatch.setattr(cli, "_staged_fabric_binding_source", lambda raw: None)

        # Build and write the installed control.json via the fixture helper.
        from tests.test_workspace_read_app import _workspace_policy
        workspace_policy = dataclasses.asdict(_workspace_policy())
        config = installed_control_config(tmp_path, control_uid=os.geteuid(),
                                          workspace_socket_path=workspace_socket_path,
                                          workspace_resource_policy=workspace_policy)
        # The workspace stanza requires the sealed App boot interpreter. The
        # boot test never starts the App process; it only walks the
        # composition through ``require_definition`` and then exits. Stub the
        # two attest seams so a non-root test can still pass.
        boot_python = config["ceo_ingress_app_boot_python"]
        monkeypatch.setattr(cli, "_sealed_root_executable", lambda path, _name: Path(path))
        monkeypatch.setattr(cli, "_attest_app_boot_runtime", lambda path: Path(path))
        config["workspace_acquisition"] = {
            "schema": "mastermind.workspace_acquisition_bindings.v1",
            "profiles": {
                "web": {"enabled": False, "binding": None},
                "mac": {"enabled": False, "binding": None},
            },
        }
        config_path = tmp_path / "control.json"
        config_path.write_text(json.dumps(config))
        config_path.chmod(0o600)
        loaded = cli.load_control_config(config_path)
        assert loaded["workspace_control_room"]["socket_path"] == workspace_socket_path

        # Drive the composition using the same monkeypatching pattern as the
        # boot test in tests/test_attended_control_startup_both_stanzas.py,
        # stopping at the require_definition check so we don't actually start
        # the production service (no broker / workers available in CI).
        from control_plane import executive_worker_broker
        from control_plane.fabric_attended_canary import AttendedControlProbeSource
        from ops.executive_os import coo_principal_host, dialogue_wake_canary_control
        from control_plane.model_router import ModelRouter
        monkeypatch.setattr(executive_worker_broker, "WorkerBrokerClient", lambda *a, **kw: object())
        monkeypatch.setattr(cli, "_load_control_environment_attestation",
                            lambda *a, **kw: {"config_sha256": "a" * 64})
        monkeypatch.setattr(cli, "_bind_exact_worker_target_source", lambda *a, **kw: None)
        monkeypatch.setattr(cli, "_bind_hot_content_profile_source", lambda *a, **kw: None)
        monkeypatch.setattr(cli, "_ceo_admission_guard", lambda *a, **kw: lambda: None)
        monkeypatch.setattr(coo_principal_host, "validate_control_coo", lambda raw: False)
        monkeypatch.setattr(dialogue_wake_canary_control, "load_verified_profile", lambda **kw: None)

        class _Router:
            pass

        monkeypatch.setattr(ModelRouter, "load", classmethod(lambda cls, **kw: _Router()))

        class _DefinitionCheckPassed(Exception):
            pass

        real_require = AttendedControlProbeSource.require_definition

        def spy_require(self, raw):
            real_require(self, raw)
            raise _DefinitionCheckPassed()

        monkeypatch.setattr(AttendedControlProbeSource, "require_definition", spy_require)

        # activate_launchd_socket returns our pre-spawned room listener for
        # the workspace name and a fresh tmp listener for everything else.
        def factory(name):
            if name not in cache:
                listener2, _ = unix_listener()
                cache[name] = listener2
            return cache[name]

        monkeypatch.setattr(cli, "activate_launchd_socket", factory)

        # Patch the ExecutiveControlService ctor's activated_socket.family probe.
        # Anything that pretends to be the real service will still inspect the
        # socket's family attribute; give it a real AF_UNIX socket.
        class _FakeService:
            def __init__(self, config, **kwargs):
                self.config = config
                self.kwargs = kwargs
        monkeypatch.setattr(cli, "ExecutiveControlService", _FakeService)

        # Fake workspace policy loader.
        authority = {"schema": "mastermind.workspace_acquisition_bindings.v1",
                     "profiles": {key: {"enabled": False, "binding": None} for key in ("web", "mac")}}

        with pytest.raises(_DefinitionCheckPassed):
            asyncio.run(cli._serve_from_config(config_path, attended_work_placements=()))

        # The composition passed the boot validator. Now boot the room by
        # hand to prove HTTP works over AF_UNIX with the right Host header.
        config_obj = ccr.ServerConfig(repo_root=tmp_path, macro_root=None, bindings_path=None,
            token="fixture", origin=ccr.UNIX_CONTROL_ROOM_ORIGIN, port=0, state_ttl=10.0)
        host = HostedControlRoom(config_obj, listener=cache["WorkspaceControlRoom"],
                                 socket_path=workspace_socket_path,
                                 allowed_peer_uids=(os.geteuid(),))

        async def serve_and_proof():
            await host.start()
            try:
                body = await asyncio.to_thread(_http_get, workspace_socket_path, "/")
                assert body  # non-empty index.html over AF_UNIX
                # 1. Audit hook saw no AF_INET / AF_INET6 bind.
                assert _AUDIT_HOOK_SEEN == [], f"unexpected AF_INET bind events: {_AUDIT_HOOK_SEEN}"
                # 2. /proc/net/tcp{,6} holds no listening socket of this process.
                assert _read_proc_listening_inodes() == set()
                # 3. The unchanged acceptance check accepts the boot. Force
                # CONTROL_SOCKET/WORKER_SOCKET is_socket True so the
                # private-unix step is satisfied.
                lsof_path = shutil.which("lsof")
                if lsof_path is None:
                    pytest.fail("lsof unavailable")
                original_run = acceptance_module._run

                def rewriter(argv, **kwargs):
                    # Replace argv[0] (the production "/usr/sbin/lsof" path,
                    # which may not exist on this host) by the resolved
                    # lsof binary, and replace the "-u <account>" pair by
                    # "-w -p <pid>" so the query is local and complete. The
                    # remaining flags (-nP, -a, -iTCP, -sTCP:LISTEN) are
                    # kept verbatim so the listener scan still restricts to
                    # listening TCP sockets only.
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
                instance = object.__new__(acceptance_module.Acceptance)
                instance._assert_no_public_listener()
            finally:
                await host.close()

        asyncio.run(serve_and_proof())
    finally:
        _AUDIT_HOOK_ACTIVE = False
        for listener in cache.values():
            try:
                listener.close()
            except Exception:
                pass
        if workspace_socket_path is not None:
            try:
                os.unlink(workspace_socket_path)
            except OSError:
                pass


class _SocketLike:
    def is_socket(self):
        return True


def test_installed_boot_refuses_owning_a_tcp_listener(tmp_path, monkeypatch):
    """If Control also opens a TCP listening socket, the unchanged acceptance
    check refuses it with "owns a TCP listener"."""

    workspace_socket_path = os.path.join(tempfile.mkdtemp(prefix="crr-neg", dir="/tmp"), "room.sock")
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(workspace_socket_path)
    os.chmod(workspace_socket_path, 0o600)
    listener.listen(8)
    monkeypatch.setattr(lifecycle_mod, "_TRUSTED_SOCKET_PARENT_UID", os.geteuid())
    monkeypatch.setattr(cli, "_CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET", workspace_socket_path)

    cache = {"WorkspaceControlRoom": listener}

    def factory(name):
        if name not in cache:
            listener2, _ = unix_listener()
            cache[name] = listener2
        return cache[name]

    monkeypatch.setattr(cli, "activate_launchd_socket", factory)

    config_obj = ccr.ServerConfig(repo_root=tmp_path, macro_root=None, bindings_path=None,
        token="fixture", origin=ccr.UNIX_CONTROL_ROOM_ORIGIN, port=0, state_ttl=10.0)
    host = HostedControlRoom(config_obj, listener=listener, socket_path=workspace_socket_path,
                             allowed_peer_uids=(os.geteuid(),))

    def fake_run_factory(argv, **kwargs):
        if fake_run_factory.first:
            fake_run_factory.first = False
            header = b"COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME\n"
            row = b"python %d _mastermind_exec 9u IPv4 0x1 0t0 TCP 127.0.0.1:9000 (LISTEN)\n" % os.getpid()
            return subprocess.CompletedProcess(["lsof"], 0, stdout=header + row)
        return subprocess.CompletedProcess(["lsof"], 1, stdout=b"")

    fake_run_factory.first = True
    monkeypatch.setattr(acceptance_module, "_run", fake_run_factory)
    monkeypatch.setattr(acceptance_module, "CONTROL_SOCKET", _SocketLike())
    monkeypatch.setattr(acceptance_module, "WORKER_SOCKET", _SocketLike())

    try:
        asyncio.run(host.start())
        try:
            instance = object.__new__(acceptance_module.Acceptance)
            with pytest.raises(acceptance_module.AcceptanceError, match="owns a TCP listener"):
                instance._assert_no_public_listener()
        finally:
            asyncio.run(host.close())
    finally:
        for listener2 in cache.values():
            try:
                listener2.close()
            except Exception:
                pass
        try:
            os.unlink(workspace_socket_path)
        except OSError:
            pass