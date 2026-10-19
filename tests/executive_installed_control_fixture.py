"""Shared helpers for the installed Control composition (CRROOM-CORE lane).

Exposes the unix listener, the unix-aware HTTP client, the new unix stanza
shape, and the full installed-control composition fixture that boots the
real ``load_control_config`` and ``_service_from_config`` end-to-end.

This module is intentionally minimal and side-effect free: it does not
import any other test module, does not start any service, and does not
require the platform to be macOS.
"""
from __future__ import annotations

import http.client
import os
import socket
import stat
import tempfile
from pathlib import Path
from typing import Iterable

import control_plane.workspace_control_room_lifecycle as lifecycle_mod
from scripts import executive_os_phase1c as cli
from scripts.chairman_control_room import UNIX_CONTROL_ROOM_HOST

__all__ = [
    "unix_listener",
    "UnixHTTPConnection",
    "unix_stanza",
    "installed_control_config",
    "spawn_workspace_room_listener",
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


def unix_listener():
    """Spawn an AF_UNIX SOCK_STREAM listening socket on a short tmp path.

    The returned ``(listener, path)`` tuple is intentionally compatible with
    the ``activate_launchd_socket`` contract: a real ``socket.socket`` whose
    ``family`` is ``AF_UNIX`` and ``type`` is ``SOCK_STREAM``, whose
    ``getsockname()`` is the bound socket path, and whose file system entry has
    mode ``0o600``. Callers clean up with the returned ``path``.
    """

    base = tempfile.mkdtemp(prefix="crr", dir="/tmp")
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
        "dialogue_observation_peer_uid": int(os.geteuid()) + 18,
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