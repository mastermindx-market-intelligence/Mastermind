"""Shared helpers for the installed Control composition (CRROOM-CORE lane).

Exposes the unix listener, the unix-aware HTTP client, the new unix stanza
shape, and the full installed-control composition fixture that boots the
real ``load_control_config`` and ``_service_from_config`` end-to-end.

This module is intentionally minimal and side-effect free: it does not
import any other test module, does not start any service, and does not
require the platform to be macOS.
"""
from __future__ import annotations

import asyncio
import dataclasses
import http.client
import json
import os
import socket
import stat
import tempfile
from pathlib import Path

import control_plane.workspace_control_room_lifecycle as lifecycle_mod
from scripts import executive_os_phase1c as cli
from scripts.chairman_control_room import UNIX_CONTROL_ROOM_HOST

__all__ = [
    "unix_listener",
    "egid_socket_dir",
    "UnixHTTPConnection",
    "unix_stanza",
    "installed_control_config",
    "spawn_workspace_room_listener",
    "BootProof",
    "boot_installed_control",
]


def spawn_workspace_room_listener(monkeypatch, *, socket_path=None):
    """Patch the canonical socket path and the parent-uid test seam so that
    ``_verify_socket_custody`` accepts a spawned AF_UNIX listener at
    ``socket_path`` (or, when None, at a fresh /tmp path).

    When ``socket_path`` is None, a fresh AF_UNIX listener is created and
    bound to that path; the caller is responsible for closing the listener
    and unlinking the path when finished. When ``socket_path`` is supplied,
    no listener is bound here — the caller must ensure a listener exists at
    that path (typically via ``fabric._workspace_aware_listener`` which
    binds one on demand).
    """

    if socket_path is None:
        listener, socket_path = unix_listener()
        monkeypatch.setattr(cli, "_CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET", socket_path)
        monkeypatch.setattr(lifecycle_mod, "_TRUSTED_SOCKET_PARENT_UID", os.geteuid())
        return listener, socket_path
    monkeypatch.setattr(cli, "_CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET", socket_path)
    monkeypatch.setattr(lifecycle_mod, "_TRUSTED_SOCKET_PARENT_UID", os.geteuid())
    return None, socket_path


def egid_socket_dir(prefix: str = "crr") -> str:
    """A fresh short directory under /tmp whose gid is this process's egid.

    BSD/macOS gives a new file its parent directory's gid (/tmp is root:wheel),
    where Linux gives the creator's egid. Production custody requires the
    socket gid to equal the configured group, so test-owned socket
    directories are re-grouped to the egid instead of loosening that check.
    """

    base = tempfile.mkdtemp(prefix=prefix, dir="/tmp")
    os.chown(base, -1, os.getegid())
    return base


def unix_listener():
    """Spawn an AF_UNIX SOCK_STREAM listening socket on a short tmp path.

    The returned ``(listener, path)`` tuple is intentionally compatible with
    the ``activate_launchd_socket`` contract: a real ``socket.socket`` whose
    ``family`` is ``AF_UNIX`` and ``type`` is ``SOCK_STREAM``, whose
    ``getsockname()`` is the bound socket path, and whose file system entry has
    mode ``0o600``. Callers clean up with the returned ``path``.
    """

    base = egid_socket_dir()
    path = os.path.join(base, "room.sock")
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(path)
    os.chmod(path, 0o600)
    listener.listen(8)
    return listener, path


class UnixHTTPConnection(http.client.HTTPConnection):
    """HTTP/1.1 connection that opens a fresh AF_UNIX stream socket per request."""

    def __init__(self, path: str, timeout: float | None = None) -> None:
        super().__init__("unix", timeout=timeout)
        self._path = path

    def connect(self) -> None:  # type: ignore[override]
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(self._path)
        self.sock = sock


def unix_stanza(control_uid: int, socket_path: str | None = None) -> dict:
    """Closed unix/launchd stanza for the workspace Control Room.

    ``socket_path`` defaults to the production canonical path so tests
    monkeypatch the module globals rather than supply their own.
    """

    from scripts import executive_os_phase1c as cli
    canonical = socket_path if socket_path is not None else cli._CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET
    return {
        "transport": "unix",
        "socket_path": canonical,
        "launchd_socket_name": cli._WORKSPACE_CONTROL_ROOM_SOCKET_NAME,
        "allowed_peer_uids": [int(control_uid)],
    }


def _writable_root(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.mkdir(exist_ok=True)
    return path


def installed_control_config(tmp_path: Path, *, control_uid: int,
                              workspace_socket_path: str,
                              workspace_resource_policy: dict | None = None) -> dict:
    """Installed Control composition fixture: control.json's complete shape.

    Carries the workspace stanza (new shape), the coordinator's principal App
    peer keys, the finite probe stanza, and the dialogue Wake retry policy
    stanza from ``tests/test_attended_control_startup_both_stanzas.py`` —
    i.e. the composition the host installs today, minus a few host-only
    filesystem roots that are replaced by ``tmp_path`` children.
    """

    runtime = _writable_root(tmp_path, "runtime")
    repo = _writable_root(tmp_path, "repo")
    macro = _writable_root(tmp_path, "macro")
    backups = _writable_root(tmp_path, "backups")
    workspace = _writable_root(tmp_path, "workspaces")
    receipts = _writable_root(tmp_path, "receipts")
    bindings = _writable_root(tmp_path, "bindings")
    fabric = _writable_root(tmp_path, "fabric-bindings")
    worker_home = _writable_root(tmp_path, "worker-home")
    runs = _writable_root(tmp_path, "runs")
    sealed_python = tmp_path / "sealed-python"
    sealed_python.write_text("#!/bin/sh\nexit 0\n")
    os.chmod(sealed_python, 0o755)
    config: dict = {
        "schema_version": "mastermind.executive_control_config/v1",
        "runtime_root": str(runtime),
        "control_socket_path": str(tmp_path / "control.sock"),
        "launchd_socket_name": "Operator",
        "ceo_ingress_socket_path": str(tmp_path / "ceo-ingress.sock"),
        "ceo_ingress_launchd_socket_name": "CeoIngress",
        "ceo_ingress_peer_uid": int(os.geteuid()) + 16,
        "worker_broker_socket_path": str(tmp_path / "worker.sock"),
        "worker_provider_home": str(worker_home),
        "worker_runs_root": str(runs),
        "receipts_root": str(receipts),
        "proof_source_repository": str(repo),
        "proof_workspace_root": str(workspace),
        "proof_base_sha": "a" * 40,
        "backup_root": str(backups),
        "control_uid": int(control_uid),
        "worker_uid": int(os.geteuid()) + 1,
        "worker_gid": int(os.geteuid()) + 1,
        "worker_user": "_mastermind_worker_fixture",
        "shared_run_gid": int(os.geteuid()) + 2,
        "allowed_peer_uids": [int(os.geteuid())],
        "secret_canary_receipt_path": str(tmp_path / "canary.json"),
        "control_environment_attestation_path": str(tmp_path / "attestation.json"),
        "ceo_ingress_app_peer_uid": int(os.geteuid()) + 17,
        "ceo_ingress_app_armed": True,
        "ceo_ingress_app_macro_root": str(macro),
        "ceo_ingress_app_boot_python": str(sealed_python),
        "executive_mcp_profile": "web_ceo_v2",
        "coo_principal_armed": True,
        "coo_principal_dialogue_armed": False,
        "workspace_acquisition": {},
        "workspace_resource_policy": workspace_resource_policy
        if workspace_resource_policy is not None else {},
        "workspace_control_room": unix_stanza(control_uid, socket_path=workspace_socket_path),
        "dialogue_observation_socket_path": "/var/run/mastermind-dialogue-observation/dialogue-observation.sock",
        "dialogue_observation_launchd_socket_name": "DialogueObservation",
        "dialogue_observation_peer_uid": 457,
        "fabric_attended_probe": {"worker_config_path": str(tmp_path / "worker.json")},
        "fabric_bindings_path": str(tmp_path / "fabric-bindings.json"),
        "fabric_bindings_sha256": "a" * 64,
        "fabric_bridge_armed": False,
        "dialogue_bridge_armed": False,
        "dialogue_wake_retry_policy": {
            "max_delivery_attempts": None,
            "retry_cooldown_s": None,
            "accepted_ttl_s": None,
            "target_unavailable_backoff_s": None,
            "reenable_on_binding_rotation": True,
            "armed": False,
        },
    }
    return config


# ---------------------------------------------------------------------------
# boot_installed_control: drive the REAL _serve_from_config through to the
# PRODUCTION room construction, replacing only ExecutiveControlService with
# a capture class. See tests/test_workspace_read_socket.py::
# test_actual_service_hosts_one_cache_before_readiness_and_drains_it for proof
# that the REAL ExecutiveControlService starts the room before READY and
# closes it on stop; the capture class mirrors those exact lines
# (control_plane/executive_service.py ~3797-3798 start, ~4031-4032 close).
# ---------------------------------------------------------------------------


class BootProof:
    """Proof object yielded by ``boot_installed_control``.

    Attributes:
        requested_names: every launchd-socket name the production code asked
            ``activate_launchd_socket`` for during this boot.
        captured_kwargs: kwargs the capture class received when production
            code constructed the ExecutiveControlService replacement.
        room: the production-constructed HostedControlRoom instance.
        room_config: ``room.config`` — the room's ServerConfig.
    """

    def __init__(self, requested_names, captured_kwargs, room, room_config):
        self.requested_names = requested_names
        self.captured_kwargs = captured_kwargs
        self.room = room
        self.room_config = room_config


def _make_sealed_python(tmp_path: Path) -> Path:
    sealed = tmp_path / "sealed-python"
    sealed.write_text("#!/bin/sh\nexit 0\n")
    os.chmod(sealed, 0o755)
    return sealed


def boot_installed_control(tmp_path, monkeypatch, root_stats, router, *, during_serve,
                           transform=None):
    """Boot the installed composition through the REAL loader and REAL composition.

    Runs ``asyncio.run(cli._serve_from_config(path, attended_work_placements=(selected(),)))``
    with the host-read patches that ``tests/test_attended_control_startup_both_stanzas.py``
    already uses (plus the workspace room recorder and the sealed-python / attest
    seams). The only thing replaced beyond those patches is ``ExecutiveControlService``,
    which is replaced with a capture class that stores its kwargs and whose
    ``serve_until_stopped`` mirrors the real service's room lifecycle exactly.

    The finite probe stanza and the dialogue Wake retry policy stanza are LIVE:
    the loader validates them, ``_staged_fabric_binding_source`` returns a real
    ``FabricBindingSource``, and ``AttendedControlProbeSource.require_definition``
    runs a real re-digest of the loaded object.

    ``root_stats`` is the same fixture the both-stanzas test uses; it makes the
    loader's root-owned checks see every test path as root-owned.

    Returns a ``BootProof``; raises whatever exception the production code raises
    if the boot cannot complete.
    """

    # root_stats is a pytest fixture from ``test_executive_fabric_composition``.
    # Its effects (Path.lstat / os.fstat -> st_uid=0) are already active on the
    # caller's monkeypatch; nothing to do here.
    _ = root_stats

    # Build the complete installed control composition from the same primitives
    # the both-stanzas test uses: _raw + staged + fabric_attended_probe + the
    # DIALOGUE stanza. Then add the workspace stanzas and the App keys.
    from tests.test_ceo_submit_armed_composition import _raw, _write
    from tests.test_executive_fabric_phase1c import staged
    from tests.test_fabric_attended_factory_placement import selected

    raw = _raw(tmp_path)
    raw.update(staged(tmp_path, raw))
    raw["fabric_attended_probe"] = {"worker_config_path": str(tmp_path / "worker.json")}
    from tests.test_attended_control_startup_both_stanzas import DIALOGUE_STANZA
    raw.update(json.loads(json.dumps(DIALOGUE_STANZA)))
    # workspace stanzas
    raw["workspace_acquisition"] = {
        "schema": "mastermind.workspace_acquisition_bindings.v1",
        "profiles": {
            "web": {"enabled": False, "binding": None},
            "mac": {"enabled": False, "binding": None},
        },
    }
    from tests.test_workspace_read_app import _workspace_policy
    raw["workspace_resource_policy"] = json.loads(json.dumps(
        dataclasses.asdict(_workspace_policy())))
    # Pre-bind the AF_UNIX listener; the production code activates it via
    # cli.activate_launchd_socket(_WORKSPACE_CONTROL_ROOM_SOCKET_NAME).
    workspace_socket_path = os.path.join(
        egid_socket_dir("crr-boot"), "room.sock")
    raw["workspace_control_room"] = unix_stanza(
        int(raw["control_uid"]), socket_path=workspace_socket_path)
    # App keys (the loader requires the entire set if workspace_acquisition
    # is present; ceo_ingress_app_boot_python is the optional App interpreter).
    raw["ceo_ingress_app_peer_uid"] = int(os.geteuid()) + 17
    raw["ceo_ingress_app_armed"] = True
    raw["ceo_ingress_app_macro_root"] = str(_writable_root(tmp_path, "macro"))
    sealed_python = _make_sealed_python(tmp_path)
    raw["ceo_ingress_app_boot_python"] = str(sealed_python)
    # CeoIngress keys (the production code activates a second launchd socket
    # for them at line 2273 when these keys are present).
    raw["ceo_ingress_socket_path"] = str(tmp_path / "ceo-ingress.sock")
    raw["ceo_ingress_launchd_socket_name"] = "CeoIngress"
    raw["ceo_ingress_peer_uid"] = int(os.geteuid()) + 16

    if transform is not None:
        raw = transform(raw)
    config_path = _write(tmp_path, raw)

    # Recorder for every launchd-socket name the production code asks for.
    requested_names: list[str] = []

    workspace_listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    workspace_listener.bind(workspace_socket_path)
    os.chmod(workspace_socket_path, 0o600)
    workspace_listener.listen(8)
    cache: dict[str, socket.socket] = {"WorkspaceControlRoom": workspace_listener}

    def activated(name):
        requested_names.append(name)
        if name not in cache:
            listener, _ = unix_listener()
            cache[name] = listener
        return cache[name]

    monkeypatch.setattr(cli, "activate_launchd_socket", activated)
    monkeypatch.setattr(cli, "_CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET", workspace_socket_path)
    monkeypatch.setattr(lifecycle_mod, "_TRUSTED_SOCKET_PARENT_UID", os.geteuid())
    # both-stanzas test host-read patches
    monkeypatch.setattr(cli, "_load_control_environment_attestation",
                        lambda *a, **kw: {"config_sha256": "a" * 64})
    monkeypatch.setattr(cli, "_bind_exact_worker_target_source", lambda *a, **kw: None)
    monkeypatch.setattr(cli, "_bind_hot_content_profile_source", lambda *a, **kw: None)
    monkeypatch.setattr(cli, "_ceo_admission_guard", lambda *a, **kw: (lambda: None))
    monkeypatch.setattr(cli, "_sealed_root_executable", lambda v, _n: Path(v))
    monkeypatch.setattr(cli, "_attest_app_boot_runtime", lambda p: Path(p))
    from control_plane import executive_worker_broker
    monkeypatch.setattr(executive_worker_broker, "WorkerBrokerClient",
                        lambda *a, **kw: object())
    from ops.executive_os import coo_principal_host, dialogue_wake_canary_control
    monkeypatch.setattr(coo_principal_host, "validate_control_coo", lambda raw: False)
    monkeypatch.setattr(dialogue_wake_canary_control, "load_verified_profile",
                        lambda **kw: None)
    from control_plane.model_router import ModelRouter
    monkeypatch.setattr(ModelRouter, "load", classmethod(lambda cls, **kw: router))

    # Capture class — mirrors the REAL ExecutiveControlService's room lifecycle
    # (control_plane/executive_service.py ~3797-3798 start, ~4031-4032 close).
    captured_kwargs: dict[str, object] = {}

    class _CaptureService:
        def __init__(self, config, **kwargs):
            self.config = config
            captured_kwargs.update(kwargs)

        async def serve_until_stopped(self):
            room = captured_kwargs.get("workspace_control_room")
            if room is not None:
                await room.start()
            try:
                await during_serve(room)
            finally:
                if room is not None:
                    await room.close()

    monkeypatch.setattr(cli, "ExecutiveControlService", _CaptureService)

    try:
        asyncio.run(cli._serve_from_config(
            config_path, attended_work_placements=(selected(),)))
    finally:
        # Close every listener we created; even on failure so we don't leak.
        for listener in cache.values():
            try:
                listener.close()
            except Exception:
                pass
        try:
            os.unlink(workspace_socket_path)
        except OSError:
            pass

    room = captured_kwargs.get("workspace_control_room")
    if room is None:
        raise RuntimeError(
            "boot_installed_control: production code did not construct a "
            "workspace_control_room; check the loader's workspace-keys gate")
    return BootProof(requested_names, captured_kwargs, room, room.config)
