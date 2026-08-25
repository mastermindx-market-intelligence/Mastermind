"""Closed boot re-attestation path for receipt-gated Executive autonomy."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.executive_os_phase1c_worker import (
    WorkerConfigError,
    _build_autonomy_canary_factory,
)


def _fixture(tmp_path: Path):
    release_sha = "a" * 40
    release = tmp_path / release_sha
    (release / "scripts").mkdir(parents=True)
    (release / "scripts" / "executive_os_phase1c_env_probe.py").write_text(
        "# fixed probe fixture\n",
        encoding="utf-8",
    )
    manifest = release / ".executive-release-manifest.json"
    manifest.write_text('{"fixture":true}\n', encoding="utf-8")
    runtime = tmp_path / "runtime"
    workspace = runtime / "jobs" / "workspaces"
    run_root = runtime / "jobs" / "runs"
    provider_home = runtime / "workers" / "codex-01" / "provider-home"
    for path in (workspace, run_root, provider_home):
        path.mkdir(parents=True)
    config = {
        "control_uid": 450,
        "worker_uid": 451,
        "worker_gid": 451,
        "worker_id": "codex-01",
        "workspace_root": str(workspace),
        "run_root": str(run_root),
        "provider_home": str(provider_home),
    }
    identity = {
        "pid": 1234,
        "pgid": 1234,
        "session_id": 1234,
        "start_identity": "Mon Aug 24 00:00:00 2026",
        "boot_id": "boot-1",
        "effective_uid": 450,
        "effective_gid": 450,
        "real_uid": 450,
        "real_gid": 450,
    }
    sentinel = "b" * 64
    attestation = {
        "schema_version": "mastermind.executive_control_environment_attestation/v1",
        "observed_at": "2026-08-24T00:00:00+00:00",
        "process_identity": identity,
        "config_sha256": "c" * 64,
        "release_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "release_commit_sha": release_sha,
        "python_executable_path": "/fixed/python",
        "python_executable_sha256": "d" * 64,
        "sentinel_name_sha256": hashlib.sha256(
            b"EXECUTIVE_CONTROL_CANARY_VALUE"
        ).hexdigest(),
        "sentinel_value_sha256": sentinel,
        "sentinel_present": True,
    }
    return release, runtime, config, attestation


def test_boot_canary_uses_fixed_probe_and_derived_protected_paths(tmp_path: Path) -> None:
    release, runtime, config, attestation = _fixture(tmp_path)
    invocations: list[list[str]] = []
    canary_configs = []

    def probe(argv):
        invocations.append(argv)
        identity = attestation["process_identity"]
        return {
            "schema_version": "mastermind.executive_control_env_probe/v1",
            "passed": True,
            "control_process_identity": identity,
            "worker_principal": {
                "real_uid": 451,
                "effective_uid": 451,
                "real_gid": 451,
                "effective_gid": 451,
            },
            "config_sha256": attestation["config_sha256"],
            "release_manifest_sha256": attestation["release_manifest_sha256"],
            "sentinel_value_sha256": attestation["sentinel_value_sha256"],
            "process_identity_sha256": hashlib.sha256(
                json.dumps(
                    identity,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest(),
            "checks": {
                "launchctl": "DENIED",
                "ps": "DENIED",
                "kern_procargs2": "DENIED",
            },
        }

    def secret_canary(value):
        canary_configs.append(value)
        return {"passed": True, "fixture": "hash-status-only"}

    issue = _build_autonomy_canary_factory(
        config,
        release_root=release,
        environment_probe_runner=probe,
        secret_canary_runner=secret_canary,
    )
    envelope = issue({"control_environment_attestation": attestation})
    assert envelope["schema_version"] == (
        "mastermind.executive_secret_canary_envelope/v1"
    )
    argv = invocations[0]
    assert str(release / "scripts" / "executive_os_phase1c_env_probe.py") in argv
    assert "--administrative-checkout-sentinel" not in argv
    assert "--executive-database" not in argv
    bound = canary_configs[0]
    assert bound.administrative_checkout_sentinel == (
        runtime
        / "control"
        / "admin-checkout"
        / ("a" * 40)
        / ".git"
        / "executive-secret-canary"
    )
    assert bound.executive_database == (
        runtime / "control" / "db" / "data" / "control_plane" / "executive.sqlite3"
    )


def test_boot_canary_rejects_stale_pid_binding_before_probe(tmp_path: Path) -> None:
    release, _runtime, config, attestation = _fixture(tmp_path)
    attestation["process_identity"] = {
        **attestation["process_identity"],
        "effective_uid": 999,
    }
    issue = _build_autonomy_canary_factory(
        config,
        release_root=release,
        environment_probe_runner=lambda _argv: pytest.fail("probe must not run"),
        secret_canary_runner=lambda _config: pytest.fail("canary must not run"),
    )
    with pytest.raises(WorkerConfigError, match="process identity"):
        issue({"control_environment_attestation": attestation})


def test_boot_canary_request_cannot_supply_paths(tmp_path: Path) -> None:
    release, _runtime, config, attestation = _fixture(tmp_path)
    issue = _build_autonomy_canary_factory(
        config,
        release_root=release,
        environment_probe_runner=lambda _argv: {},
        secret_canary_runner=lambda _config: {},
    )
    with pytest.raises(WorkerConfigError, match="fields differ"):
        issue(
            {
                "control_environment_attestation": attestation,
                "administrative_checkout_sentinel": "/tmp/operator-choice",
            }
        )
