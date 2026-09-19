from __future__ import annotations

import io
import subprocess

import pytest

from ops.executive_os import secondary_host_power_policy as power


def _completed(command: tuple[str, ...], *, rc: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, rc, stdout, "")


def test_non_root_refuses_before_any_command() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return _completed(command)

    with pytest.raises(power.SecondaryHostPowerPolicyError):
        power.prepare_secondary_host_power_policy(runner=runner, euid=501)
    assert calls == []


def test_exact_fixed_charger_policy_then_readback() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command == power.PMSET_SET_COMMAND:
            return _completed(command)
        assert command == power.PMSET_READ_COMMAND
        return _completed(command, stdout="AC Power:\n sleep 0\n autorestart 1\n")

    receipt = power.prepare_secondary_host_power_policy(runner=runner, euid=0)

    assert calls == [power.PMSET_SET_COMMAND, power.PMSET_READ_COMMAND]
    assert receipt == {
        "schema": power.RECEIPT_SCHEMA,
        "scope": "charger",
        "sleep": 0,
        "autorestart": 1,
    }


@pytest.mark.parametrize(
    "stdout",
    [
        "AC Power:\n sleep 1\n autorestart 1\n",
        "AC Power:\n sleep 0\n autorestart 0\n",
        "AC Power:\n sleep 0\n",
        "Battery Power:\n sleep 0\n autorestart 1\n",
        "not pmset output\n",
    ],
)
def test_post_write_readback_must_exactly_satisfy_fleet_predicates(stdout: str) -> None:
    def runner(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        if command == power.PMSET_SET_COMMAND:
            return _completed(command)
        return _completed(command, stdout=stdout)

    with pytest.raises(power.SecondaryHostPowerPolicyError):
        power.prepare_secondary_host_power_policy(runner=runner, euid=0)


def test_failed_mutation_never_attempts_success_readback() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return _completed(command, rc=1)

    with pytest.raises(power.SecondaryHostPowerPolicyError):
        power.prepare_secondary_host_power_policy(runner=runner, euid=0)
    assert calls == [power.PMSET_SET_COMMAND]


def test_readback_failure_refuses() -> None:
    def runner(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        if command == power.PMSET_SET_COMMAND:
            return _completed(command)
        return _completed(command, rc=1)

    with pytest.raises(power.SecondaryHostPowerPolicyError):
        power.prepare_secondary_host_power_policy(runner=runner, euid=0)


def test_cli_rejects_arguments_without_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        power,
        "prepare_secondary_host_power_policy",
        lambda: pytest.fail("effect should not run"),
    )
    assert power.main(["--anything"], stdout=io.StringIO(), stderr=io.StringIO()) == 64


def test_cli_success_is_secret_free_canonical_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        power,
        "prepare_secondary_host_power_policy",
        lambda: {
            "schema": power.RECEIPT_SCHEMA,
            "scope": "charger",
            "sleep": 0,
            "autorestart": 1,
        },
    )
    stdout = io.StringIO()
    stderr = io.StringIO()
    assert power.main([], stdout=stdout, stderr=stderr) == 0
    assert stderr.getvalue() == ""
    assert stdout.getvalue() == (
        '{"autorestart":1,"schema":"mastermind.secondary_host_power_policy_receipt/v1",'
        '"scope":"charger","sleep":0}\n'
    )
