from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from control_plane.remote_attempt_transport import RemoteWorkerHostBinding
from ops.executive_os.remote_worker_binding_source import (
    BINDING_SOURCE_SCHEMA,
    RemoteWorkerBindingSourceError,
    RootManagedRemoteWorkerBindingSource,
)
from scripts import executive_os_phase1c as control
from test_ceo_submit_armed_composition import _raw as control_raw, _write as write_control

HOST = "host-" + "a" * 64
WORKER = "dot2api-01"


def _file(path: Path, body: bytes, mode: int) -> Path:
    path.write_bytes(body)
    path.chmod(mode)
    os.chown(path, os.geteuid(), path.stat().st_gid)
    return path


def _document(tmp_path: Path) -> tuple[Path, dict]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    ca = _file(tmp_path / "ca.pem", b"fixture-ca", 0o440)
    cert = _file(tmp_path / "client.pem", b"fixture-cert", 0o440)
    key = _file(tmp_path / "client.key", b"fixture-key", 0o400)
    value = {
        "schema": BINDING_SOURCE_SCHEMA,
        "bindings": [
            {
                "host_ref": HOST,
                "worker_id": WORKER,
                "adapter_id": "dot2api",
                "worker_user": "_mastermind_dot2api",
                "worker_uid": 459,
                "worker_gid": 459,
                "endpoint_host": "10.0.0.10",
                "endpoint_port": 7443,
                "ca_path": str(ca),
                "client_cert_path": str(cert),
                "client_key_path": str(key),
                "expected_server_fingerprint": "b" * 64,
                "timeout_seconds": 30.0,
                "secret_canary_verdict": {
                    "passed": True,
                    "worker_id": WORKER,
                    "receipt_sha256": "c" * 64,
                },
            }
        ],
    }
    path = tmp_path / "bindings.json"
    _replace_document(path, value)
    os.chown(path, os.geteuid(), path.stat().st_gid)
    return path, value


def _replace_document(path: Path, value: dict, *, mode: int = 0o440) -> None:
    replacement = path.with_name(path.name + ".next")
    replacement.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    replacement.chmod(mode)
    gid = path.stat().st_gid if path.exists() else path.parent.stat().st_gid
    os.chown(replacement, os.geteuid(), gid)
    os.replace(replacement, path)


def _source(path: Path) -> RootManagedRemoteWorkerBindingSource:
    info = path.stat()
    return RootManagedRemoteWorkerBindingSource(
        path,
        expected_owner_uid=info.st_uid,
        expected_group_gid=info.st_gid,
    )


def test_root_binding_source_returns_only_exact_host_worker_pair(tmp_path: Path) -> None:
    path, _ = _document(tmp_path)
    source = _source(path)
    binding = source(HOST, WORKER)
    assert type(binding) is RemoteWorkerHostBinding
    assert binding.host_ref == HOST
    assert binding.worker_id == WORKER
    assert binding.adapter_id == "dot2api"
    assert binding.transport.endpoint == ("10.0.0.10", 7443)
    assert binding.worker_uid == 459
    assert binding.secret_canary_verdict["passed"] is True
    assert source(HOST, "foreign-worker") is None
    assert source("host-" + "d" * 64, WORKER) is None


def test_root_binding_source_rereads_rotation_and_refuses_ambiguous_rows(tmp_path: Path) -> None:
    path, value = _document(tmp_path)
    source = _source(path)
    first = source(HOST, WORKER)
    assert first is not None and first.transport.expected_server_fingerprint == "b" * 64

    changed = json.loads(json.dumps(value))
    changed["bindings"][0]["expected_server_fingerprint"] = "d" * 64
    _replace_document(path, changed)
    rotated = source(HOST, WORKER)
    assert rotated is not None and rotated.transport.expected_server_fingerprint == "d" * 64

    duplicated = json.loads(json.dumps(changed))
    duplicated["bindings"].append(dict(duplicated["bindings"][0]))
    _replace_document(path, duplicated)
    with pytest.raises(RemoteWorkerBindingSourceError, match="duplicate|ordered"):
        source(HOST, WORKER)


def test_root_binding_source_refuses_secret_fields_and_weak_files(tmp_path: Path) -> None:
    path, value = _document(tmp_path)
    value["bindings"][0]["secret_canary_verdict"]["api_token"] = "forbidden"
    _replace_document(path, value)
    with pytest.raises(RemoteWorkerBindingSourceError, match="secret"):
        _source(path)(HOST, WORKER)

    weak_root = tmp_path / "weak"
    weak_root.mkdir()
    path, value = _document(weak_root)
    _replace_document(path, value, mode=0o664)
    with pytest.raises(RemoteWorkerBindingSourceError, match="identity"):
        _source(path)(HOST, WORKER)


def test_control_config_builds_real_remote_binding_source_only_when_configured(tmp_path: Path) -> None:
    path, _ = _document(tmp_path)
    assert control._remote_worker_binding_source_from_config({}) is None
    calls = []

    def factory(source_path, **kwargs):
        calls.append((source_path, kwargs))
        return "source"

    result = control._remote_worker_binding_source_from_config(
        {"remote_worker_bindings_path": path}, factory=factory
    )
    assert result == "source"
    assert calls == [
        (
            path,
            {"expected_owner_uid": 0, "expected_group_gid": os.getegid()},
        )
    ]


def test_control_config_accepts_optional_remote_binding_projection(tmp_path: Path) -> None:
    binding_path, _ = _document(tmp_path / "binding")
    raw = control_raw(tmp_path)
    raw["remote_worker_bindings_path"] = str(binding_path)
    loaded = control.load_control_config(write_control(tmp_path, raw))
    assert loaded["remote_worker_bindings_path"] == binding_path.resolve(strict=False)
