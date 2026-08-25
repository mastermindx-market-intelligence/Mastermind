"""Host-policy tests for the root-only Executive autonomy control surface."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from control_plane.executive_autonomy import StatusEvidence
from ops.executive_os import autonomy_control as control


SHA = "c" * 40
NOW = datetime(2026, 8, 24, 12, 0, 0, tzinfo=UTC)


class FakeStatusHost:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = []

    def collect_status(self, expected_sha, *, now):
        self.calls.append((expected_sha, now))
        return self.snapshot


def _snapshot(**overrides):
    evidence_values = {
        "transaction_present": False,
        "control_armed": False,
        "worker_armed": False,
        "receipt_state": None,
        "receipt_matches": False,
        "config_drift": False,
        "identity_reconciled": True,
        "service_state": "STOPPED",
        "readiness_expires_at": None,
    }
    evidence_values.update(overrides.pop("evidence", {}))
    values = {
        "expected_sha": SHA,
        "installed_sha": SHA,
        "control_config_sha256": "1" * 64,
        "worker_config_sha256": "2" * 64,
        "evidence": StatusEvidence(**evidence_values),
        "refusal_code": None,
    }
    values.update(overrides)
    return control.StatusSnapshot(**values)


def test_parser_exposes_only_closed_commands_and_bounded_arguments():
    parser = control._parser()
    status = parser.parse_args(["status", "--expected-sha", SHA])
    assert vars(status) == {"command": "status", "expected_sha": SHA}

    arm = parser.parse_args(
        [
            "arm",
            "--expected-sha",
            SHA,
            "--gate-b-receipt",
            "/private/tmp/gate-b.json",
            "--expected-credential-kind",
            "device-auth",
            "--workspace-binding-class",
            "company-workspace-admin-attested",
            "--credential-expires-at",
            "2026-08-25T12:00:00Z",
        ]
    )
    assert vars(arm) == {
        "command": "arm",
        "expected_sha": SHA,
        "gate_b_receipt": Path("/private/tmp/gate-b.json"),
        "expected_credential_kind": "device-auth",
        "workspace_binding_class": "company-workspace-admin-attested",
        "credential_expires_at": "2026-08-25T12:00:00Z",
    }

    disarm = parser.parse_args(["disarm", "--expected-sha", SHA])
    assert vars(disarm) == {"command": "disarm", "expected_sha": SHA}

    help_text = parser.format_help()
    for forbidden in (
        "--system-root",
        "--runtime-root",
        "--config-path",
        "--receipt-path",
        "--service-label",
        "--release-root",
        "--command-path",
    ):
        assert forbidden not in help_text


@pytest.mark.parametrize("bad_sha", ["", "abc", "C" * 40, "f" * 39, "g" * 40])
def test_parser_rejects_non_exact_lowercase_commit_sha(bad_sha):
    with pytest.raises(SystemExit):
        control._parser().parse_args(["status", "--expected-sha", bad_sha])


def test_parser_rejects_duplicate_expected_sha_instead_of_using_last_value():
    with pytest.raises(SystemExit):
        control._parser().parse_args(
            ["status", "--expected-sha", SHA, "--expected-sha", "d" * 40]
        )


def test_production_paths_and_service_identities_are_not_caller_selectable():
    assert control.SYSTEM_ROOT == Path(
        "/Library/Application Support/MastermindExecutive"
    )
    assert control.RUNTIME_ROOT == Path("/var/db/mastermind-executive")
    assert control.CONTROL_CONFIG == control.SYSTEM_ROOT / "config/control.json"
    assert control.WORKER_CONFIG == control.SYSTEM_ROOT / "config/worker-codex.json"
    assert control.AUTONOMY_RECEIPT == control.SYSTEM_ROOT / "config/autonomy-state-v1.json"
    assert control.AUTONOMY_TRANSACTION == control.SYSTEM_ROOT / "config/autonomy-transaction.lock"
    assert control.CONTROL_LABEL == "com.mastermind.executive.control"
    assert control.WORKER_LABEL == "com.mastermind.executive.worker.codex"


def test_status_returns_one_sanitized_unarmed_document(capsys):
    host = FakeStatusHost(_snapshot())
    result = control.main(
        ["status", "--expected-sha", SHA], host=host, now=lambda: NOW
    )

    assert result == 0
    assert host.calls == [(SHA, NOW)]
    document = json.loads(capsys.readouterr().out)
    assert document == {
        "config": {
            "control_armed": False,
            "control_sha256": "1" * 64,
            "worker_armed": False,
            "worker_sha256": "2" * 64,
        },
        "expected_sha": SHA,
        "installed_sha": SHA,
        "readiness_expires_at": None,
        "receipt_state": None,
        "refusal_code": None,
        "schema_version": control.STATUS_SCHEMA_VERSION,
        "service_state": "STOPPED",
        "status": "UNARMED",
    }


def test_status_returns_armed_ready_only_for_exact_matching_evidence(capsys):
    host = FakeStatusHost(
        _snapshot(
            evidence={
                "control_armed": True,
                "worker_armed": True,
                "receipt_state": "ARMED",
                "receipt_matches": True,
                "service_state": "READY",
                "readiness_expires_at": NOW + timedelta(hours=2),
            }
        )
    )
    assert (
        control.main(["status", "--expected-sha", SHA], host=host, now=lambda: NOW)
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "ARMED_READY"
    assert output["readiness_expires_at"] == "2026-08-24T14:00:00Z"


@pytest.mark.parametrize(
    ("evidence", "expected"),
    [
        ({"transaction_present": True}, "TRANSACTION_INCOMPLETE"),
        ({"control_armed": True}, "CONFIG_DRIFT"),
        ({"identity_reconciled": False}, "EFFECT_UNKNOWN"),
        (
            {
                "control_armed": True,
                "worker_armed": True,
                "receipt_state": "ARMED",
                "receipt_matches": True,
                "readiness_expires_at": NOW,
            },
            "READINESS_EXPIRED",
        ),
        (
            {
                "control_armed": True,
                "worker_armed": True,
                "receipt_state": "ARMED",
                "receipt_matches": True,
                "readiness_expires_at": NOW + timedelta(minutes=20),
            },
            "ARMED_DEGRADED",
        ),
    ],
)
def test_adverse_status_is_closed_nonzero_and_has_no_traceback(
    evidence, expected, capsys
):
    host = FakeStatusHost(_snapshot(evidence=evidence, refusal_code="closed_refusal"))
    result = control.main(
        ["status", "--expected-sha", SHA], host=host, now=lambda: NOW
    )
    captured = capsys.readouterr()
    assert result == 2
    assert "Traceback" not in captured.out + captured.err
    assert json.loads(captured.out)["status"] == expected
    assert json.loads(captured.out)["refusal_code"] == "closed_refusal"


def test_status_host_failure_is_effect_unknown_and_sanitized(capsys):
    class BrokenHost:
        def collect_status(self, expected_sha, *, now):
            raise control.HostControlError("installed_identity_unavailable")

    result = control.main(
        ["status", "--expected-sha", SHA], host=BrokenHost(), now=lambda: NOW
    )
    captured = capsys.readouterr()
    assert result == 2
    assert captured.err == ""
    document = json.loads(captured.out)
    assert document["status"] == "EFFECT_UNKNOWN"
    assert document["refusal_code"] == "installed_identity_unavailable"
    assert "Traceback" not in captured.out


def test_status_document_contains_no_path_command_or_secret_fields():
    document = control.status_document(_snapshot(), now=NOW)
    encoded = json.dumps(document, sort_keys=True).lower()
    for forbidden in (
        "token",
        "cookie",
        "password",
        "prompt",
        "provider_home",
        "auth.json",
        "/library/",
        "/var/db/",
        "launchctl",
        "process_args",
    ):
        assert forbidden not in encoded


def test_wrapper_and_installer_keep_the_control_surface_fixed_and_unarmed():
    root = Path(__file__).resolve().parents[1]
    wrapper = (root / "ops/executive_os/autonomy-control.sh").read_text(
        encoding="utf-8"
    )
    install = (root / "ops/executive_os/install.sh").read_text(encoding="utf-8")

    assert "autonomy_control.py" in wrapper
    assert '"$PYTHON_BINARY" -I -S -B' in wrapper
    assert "must run as root" in wrapper
    assert "exact installed release" in wrapper
    assert "exec " in wrapper
    for forbidden in ("eval ", "bash -c", "sh -c", "curl ", "security "):
        assert forbidden not in wrapper

    assert '"coo_autonomy_armed": False' in install
    assert '"coo_operator_harness_armed": False' in install
    assert "autonomy-control.sh" in install
    assert "autonomy_control.py" in install
