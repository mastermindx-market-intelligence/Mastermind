from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from control_plane.worker_adapter import adapter_descriptor
from ops.executive_os.dot2api_worker_service import (
    CONFIG_SCHEMA_VERSION,
    Dot2ApiWorkerServiceError,
    build_dot2api_worker_broker,
    load_dot2api_worker_config,
    main,
    read_dot2api_token,
)

ROOT = Path(__file__).resolve().parents[1]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> tuple[Path, dict]:
    if os.geteuid() == 0:
        pytest.skip("worker-service identity fixture requires a non-root test user")
    workspace = tmp_path / "workspace"
    run_root = tmp_path / "runs"
    provider_home = tmp_path / "provider"
    for path in (workspace, run_root, provider_home):
        path.mkdir(mode=0o700)
    token = provider_home / "dot2api.token"
    token.write_text("dot2api-fixture-secret\n", encoding="utf-8")
    token.chmod(0o600)
    os.chown(token, os.geteuid(), os.getegid())
    transport = ROOT / "ops" / "executive_os" / "dot2api_transport_worker.py"
    python = Path(sys.executable).resolve(strict=True)
    value = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "control_uid": os.geteuid() + 1000,
        "worker_uid": os.geteuid(),
        "worker_gid": os.getegid(),
        "allowed_supplementary_gids": [],
        "worker_user": "fixture-dot-worker",
        "worker_id": "dot2api-01",
        "workspace_root": str(workspace),
        "run_root": str(run_root),
        "provider_home": str(provider_home),
        "python_binary": str(python),
        "python_binary_sha256": _sha(python),
        "transport_script_sha256": _sha(transport),
        "dot2api_base_url": "http://127.0.0.1:8788",
        "dot2api_token_path": str(token),
        "queue": "dot",
        "poll_seconds": 1.0,
        "submission_timeout_seconds": 30.0,
        "launchd_socket_name": "WorkerBroker",
        "uid_sweep_receipt": str(run_root / "uid-sweep.json"),
        "require_secret_canary": True,
        "operator_harness_armed": False,
    }
    config = tmp_path / "dot2api-worker.json"
    config.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    config.chmod(0o600)
    return config, value


def test_dot2api_worker_service_config_and_broker_are_exact(tmp_path: Path) -> None:
    config_path, value = _fixture(tmp_path)
    config = load_dot2api_worker_config(config_path, require_root_owner=False)
    assert config.schema_version == CONFIG_SCHEMA_VERSION
    assert config.worker_id == "dot2api-01"
    assert config.dot2api_base_url == "http://127.0.0.1:8788"
    assert config.queue == "dot"
    assert config.operator_harness_armed is False

    assert adapter_descriptor("dot2api").implemented is False
    broker = build_dot2api_worker_broker(config, release_root=ROOT)
    assert broker.adapter_id == "dot2api"
    assert broker.validation_adapter_id == "dot2api"
    assert broker.operator_harness_armed is False
    assert broker.policy.worker_id == value["worker_id"]
    assert broker.policy.require_secret_canary is True


def test_dot2api_worker_service_token_is_private_and_rotation_safe(tmp_path: Path) -> None:
    config_path, value = _fixture(tmp_path)
    config = load_dot2api_worker_config(config_path, require_root_owner=False)
    assert read_dot2api_token(config) == "dot2api-fixture-secret"

    token = Path(value["dot2api_token_path"])
    replacement = token.with_suffix(".next")
    replacement.write_text("rotated-dot2api-secret\n", encoding="utf-8")
    replacement.chmod(0o600)
    os.chown(replacement, os.geteuid(), os.getegid())
    os.replace(replacement, token)
    assert read_dot2api_token(config) == "rotated-dot2api-secret"

    token.chmod(0o644)
    with pytest.raises(Dot2ApiWorkerServiceError, match="credential"):
        read_dot2api_token(config)


def test_dot2api_worker_service_refuses_public_origin_and_path_escape(tmp_path: Path) -> None:
    config_path, value = _fixture(tmp_path)
    for mutate in (
        lambda row: row.__setitem__("dot2api_base_url", "https://dot.example.com"),
        lambda row: row.__setitem__("dot2api_token_path", str(tmp_path / "outside.token")),
        lambda row: row.__setitem__("operator_harness_armed", True),
    ):
        changed = copy.deepcopy(value)
        mutate(changed)
        config_path.write_text(json.dumps(changed, sort_keys=True), encoding="utf-8")
        with pytest.raises(Dot2ApiWorkerServiceError):
            load_dot2api_worker_config(config_path, require_root_owner=False)


def test_dot2api_worker_service_refuses_release_identity_drift(tmp_path: Path) -> None:
    config_path, value = _fixture(tmp_path)
    for field in ("python_binary_sha256", "transport_script_sha256"):
        changed = copy.deepcopy(value)
        changed[field] = "0" * 64
        config_path.write_text(json.dumps(changed, sort_keys=True), encoding="utf-8")
        config = load_dot2api_worker_config(config_path, require_root_owner=False)
        with pytest.raises(Dot2ApiWorkerServiceError, match="digest"):
            build_dot2api_worker_broker(config, release_root=ROOT)


def test_dot2api_worker_check_config_is_sanitized(tmp_path: Path, capsys) -> None:
    config_path, _value = _fixture(tmp_path)
    rc = main(
        [
            "check-config",
            "--config",
            str(config_path),
            "--allow-non-root-owner-for-test",
        ],
        release_root=ROOT,
    )
    assert rc == 0
    output = capsys.readouterr()
    row = json.loads(output.out)
    assert row == {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "valid": True,
        "worker_id": "dot2api-01",
        "worker_uid": os.geteuid(),
        "launchd_socket_name": "WorkerBroker",
    }
    assert "fixture-secret" not in output.out + output.err
