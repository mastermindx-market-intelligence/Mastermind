"""Adversarial tests for the content-blind distinct-principal canary."""

from __future__ import annotations

import dataclasses
import errno
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from control_plane.codex_worker import validate_secret_canary_verdict
from control_plane.executive_canary import (
    REQUIRED_CHECKS,
    WORKER_AUTH_EXCEPTION,
    PrincipalIdentity,
    SecretCanaryConfig,
    SecretCanaryError,
    run_secret_canary,
    validate_secret_canary_binding,
)
from scripts import executive_os_phase1c_canary as canary_cli

_OBSERVED_AT = datetime(2026, 8, 11, 20, 30, 40, tzinfo=UTC)


def _config() -> SecretCanaryConfig:
    return SecretCanaryConfig(
        expected_worker_uid=502,
        expected_worker_gid=503,
        control_uid=501,
        control_gid=20,
        control_environment_sentinel="EXECUTIVE_CONTROL_CANARY_VALUE",
        control_environment_probe_sha256="c" * 64,
        administrative_checkout_sentinel=Path("/admin/RAW_ADMIN_SENTINEL"),
        executive_database=Path("/control/RAW_EXECUTIVE.sqlite3"),
        other_worker_home_sentinel=Path("/workers/other/RAW_HOME_SENTINEL"),
        forbidden_production_sentinel=Path("/production/RAW_PRODUCTION_SENTINEL"),
        codex_home=Path("/workers/codex/RAW_CODEX_HOME"),
    )


def _principal() -> PrincipalIdentity:
    return PrincipalIdentity(
        real_uid=502,
        effective_uid=502,
        real_gid=503,
        effective_gid=503,
    )


def _expected_open_paths(config: SecretCanaryConfig) -> list[Path]:
    database = config.executive_database
    return [
        config.administrative_checkout_sentinel,
        database,
        database.with_name(database.name + "-wal"),
        database.with_name(database.name + "-shm"),
        database.with_name(database.name + "-journal"),
        config.other_worker_home_sentinel,
        config.forbidden_production_sentinel,
        config.codex_home / "auth.json",
    ]


def _cli_arguments(config: SecretCanaryConfig) -> list[str]:
    return [
        "--expected-worker-uid",
        str(config.expected_worker_uid),
        "--expected-worker-gid",
        str(config.expected_worker_gid),
        "--control-uid",
        str(config.control_uid),
        "--control-gid",
        str(config.control_gid),
        "--control-env-sentinel",
        config.control_environment_sentinel,
        "--control-environment-probe-sha256",
        config.control_environment_probe_sha256,
        "--administrative-checkout-sentinel",
        os.fspath(config.administrative_checkout_sentinel),
        "--executive-database",
        os.fspath(config.executive_database),
        "--other-worker-home-sentinel",
        os.fspath(config.other_worker_home_sentinel),
        "--forbidden-production-sentinel",
        os.fspath(config.forbidden_production_sentinel),
        "--codex-home",
        os.fspath(config.codex_home),
    ]


def _passing_probe(config: SecretCanaryConfig):
    calls: list[tuple[Path, int]] = []
    closed: list[int] = []
    auth_path = config.codex_home / "auth.json"

    def opener(path: Path, flags: int) -> int:
        calls.append((path, flags))
        if path == auth_path:
            return 101
        denied_errno = errno.EACCES if len(calls) % 2 else errno.EPERM
        raise PermissionError(denied_errno, "permission denied")

    def closer(descriptor: int) -> None:
        closed.append(descriptor)

    verdict = run_secret_canary(
        config,
        opener=opener,
        closer=closer,
        environment={},
        principal=_principal(),
        clock=lambda: _OBSERVED_AT,
    )
    return verdict, calls, closed


def test_passing_canary_is_validator_compatible_hash_status_only_and_open_only():
    config = _config()

    verdict, calls, closed = _passing_probe(config)

    assert set(verdict) == {
        "schema_version",
        "passed",
        "checks",
        "receipt_sha256",
        "control_environment_probe_sha256",
        "observed_at",
        "worker_auth_exception",
    }
    assert verdict["passed"] is True
    assert verdict["checks"] == dict.fromkeys(REQUIRED_CHECKS, "DENIED")
    assert verdict["observed_at"] == "2026-08-11T20:30:40Z"
    assert verdict["worker_auth_exception"] == WORKER_AUTH_EXCEPTION
    assert verdict["control_environment_probe_sha256"] == "c" * 64
    assert len(verdict["receipt_sha256"]) == 64
    assert validate_secret_canary_verdict(verdict, require_passed=True) == verdict
    assert [path for path, _flags in calls] == _expected_open_paths(config)
    assert all(flags & (os.O_WRONLY | os.O_RDWR) == 0 for _path, flags in calls)
    assert closed == [101]

    serialized = json.dumps(verdict, sort_keys=True)
    forbidden_content = {
        config.control_environment_sentinel,
        *map(os.fspath, _expected_open_paths(config)),
        "RAW_ADMIN_SENTINEL",
        "RAW_EXECUTIVE.sqlite3",
        "RAW_HOME_SENTINEL",
        "RAW_PRODUCTION_SENTINEL",
        "RAW_CODEX_HOME",
    }
    assert all(value not in serialized for value in forbidden_content)


def test_receipt_hash_is_deterministic_and_binds_exact_probe_configuration():
    config = _config()
    first, _calls, _closed = _passing_probe(config)
    second, _calls, _closed = _passing_probe(config)
    changed, _calls, _closed = _passing_probe(
        dataclasses.replace(
            config,
            forbidden_production_sentinel=Path("/production/a-different-sentinel"),
        )
    )

    assert first == second
    assert first["receipt_sha256"] != changed["receipt_sha256"]
    changed_probe, _calls, _closed = _passing_probe(
        dataclasses.replace(
            config,
            control_environment_probe_sha256="d" * 64,
        )
    )
    assert first["receipt_sha256"] != changed_probe["receipt_sha256"]


def test_binding_validator_recomputes_probe_and_receipt_commitments():
    config = _config()
    verdict, _calls, _closed = _passing_probe(config)

    assert validate_secret_canary_binding(config, _principal(), verdict) == verdict

    with pytest.raises(SecretCanaryError, match="CANARY_CONTROL_PROBE_BINDING_MISMATCH"):
        validate_secret_canary_binding(
            dataclasses.replace(config, control_environment_probe_sha256="d" * 64),
            _principal(),
            verdict,
        )
    with pytest.raises(SecretCanaryError, match="CANARY_RECEIPT_BINDING_MISMATCH"):
        validate_secret_canary_binding(
            config,
            _principal(),
            {**verdict, "receipt_sha256": "e" * 64},
        )


@pytest.mark.parametrize(
    ("config", "principal", "code"),
    [
        (
            dataclasses.replace(_config(), expected_worker_uid=0),
            _principal(),
            "CANARY_EXPECTED_PRINCIPAL_IS_ROOT",
        ),
        (
            dataclasses.replace(_config(), expected_worker_gid=0),
            _principal(),
            "CANARY_EXPECTED_PRINCIPAL_IS_ROOT",
        ),
        (
            dataclasses.replace(_config(), control_uid=502),
            _principal(),
            "CANARY_PRINCIPALS_NOT_DISTINCT",
        ),
        (
            dataclasses.replace(_config(), control_gid=503),
            _principal(),
            "CANARY_PRINCIPALS_NOT_DISTINCT",
        ),
        (
            _config(),
            dataclasses.replace(_principal(), effective_uid=504),
            "CANARY_PRINCIPAL_MISMATCH",
        ),
        (
            _config(),
            dataclasses.replace(_principal(), real_gid=504),
            "CANARY_PRINCIPAL_MISMATCH",
        ),
    ],
)
def test_principal_must_be_non_root_exact_and_distinct(config, principal, code):
    opened = False

    def opener(_path: Path, _flags: int) -> int:
        nonlocal opened
        opened = True
        return 1

    with pytest.raises(SecretCanaryError, match=f"^{code}$"):
        run_secret_canary(config, opener=opener, environment={}, principal=principal)
    assert opened is False


def test_visible_control_environment_sentinel_fails_without_reading_its_value():
    config = _config()

    class PresenceOnlyEnvironment(dict):
        def __getitem__(self, key):
            pytest.fail(f"canary tried to read environment value for {key!r}")

    environment = PresenceOnlyEnvironment(
        {config.control_environment_sentinel: "RAW_CONTROL_SECRET_VALUE"}
    )
    with pytest.raises(
        SecretCanaryError, match="^CANARY_CONTROL_ENVIRONMENT_VISIBLE$"
    ) as captured:
        run_secret_canary(config, environment=environment, principal=_principal())

    assert "RAW_CONTROL_SECRET_VALUE" not in str(captured.value)
    assert config.control_environment_sentinel not in str(captured.value)


@pytest.mark.parametrize(
    ("target_index", "outcome", "code"),
    [
        (0, "missing", "CANARY_PROTECTED_OPEN_NOT_PERMISSION_DENIED"),
        (2, "readable", "CANARY_PROTECTED_OPEN_UNEXPECTEDLY_SUCCEEDED"),
        (4, "io-error", "CANARY_PROTECTED_OPEN_NOT_PERMISSION_DENIED"),
    ],
)
def test_missing_readable_or_non_permission_denied_protected_target_fails_closed(
    target_index, outcome, code
):
    config = _config()
    target = _expected_open_paths(config)[target_index]
    closed: list[int] = []

    def opener(path: Path, _flags: int) -> int:
        if path != target:
            raise PermissionError(errno.EACCES, "permission denied")
        if outcome == "missing":
            raise FileNotFoundError(errno.ENOENT, "missing")
        if outcome == "io-error":
            raise OSError(errno.EIO, "I/O failure")
        return 202

    with pytest.raises(SecretCanaryError, match=f"^{code}$") as captured:
        run_secret_canary(
            config,
            opener=opener,
            closer=closed.append,
            environment={},
            principal=_principal(),
        )

    assert os.fspath(target) not in str(captured.value)
    assert closed == ([202] if outcome == "readable" else [])


def test_dedicated_auth_must_open_but_is_never_read_or_exposed():
    config = _config()
    auth_path = config.codex_home / "auth.json"
    calls: list[Path] = []

    def opener(path: Path, _flags: int) -> int:
        calls.append(path)
        if path == auth_path:
            raise PermissionError(errno.EACCES, "permission denied")
        raise PermissionError(errno.EPERM, "operation not permitted")

    with pytest.raises(
        SecretCanaryError, match="^CANARY_DEDICATED_AUTH_NOT_OPENABLE$"
    ) as captured:
        run_secret_canary(
            config,
            opener=opener,
            environment={},
            principal=_principal(),
        )

    assert calls[-1] == auth_path
    assert os.fspath(auth_path) not in str(captured.value)


def test_relative_cli_paths_are_rejected_and_success_prints_only_json(
    monkeypatch, capsys
):
    with pytest.raises(SystemExit):
        canary_cli._parser().parse_args(
            [
                "--expected-worker-uid",
                "502",
                "--expected-worker-gid",
                "503",
                "--control-uid",
                "501",
                "--control-gid",
                "20",
                "--control-env-sentinel",
                "EXECUTIVE_CONTROL_CANARY_VALUE",
                "--administrative-checkout-sentinel",
                "relative/path",
                "--executive-database",
                "/control/db",
                "--other-worker-home-sentinel",
                "/worker/sentinel",
                "--forbidden-production-sentinel",
                "/production/sentinel",
                "--codex-home",
                "/worker/codex-home",
            ]
        )
    capsys.readouterr()

    expected, _calls, _closed = _passing_probe(_config())
    monkeypatch.setattr(canary_cli, "run_secret_canary", lambda _config: expected)
    config = _config()
    exit_code = canary_cli.main(_cli_arguments(config))
    output = capsys.readouterr()

    assert exit_code == 0
    assert output.err == ""
    assert json.loads(output.out) == expected


def test_cli_failure_has_no_partial_verdict_or_configured_path_leak(
    monkeypatch, capsys
):
    config = _config()

    def fail(_config):
        raise SecretCanaryError("CANARY_PROTECTED_OPEN_UNEXPECTEDLY_SUCCEEDED")

    monkeypatch.setattr(canary_cli, "run_secret_canary", fail)

    assert canary_cli.main(_cli_arguments(config)) == 1
    output = capsys.readouterr()

    assert output.out == ""
    assert output.err == (
        "secret canary failed: CANARY_PROTECTED_OPEN_UNEXPECTEDLY_SUCCEEDED\n"
    )
    assert all(
        os.fspath(path) not in output.err for path in _expected_open_paths(config)
    )
