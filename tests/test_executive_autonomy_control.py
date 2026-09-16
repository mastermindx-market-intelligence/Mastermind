"""Host-policy tests for the root-only Executive autonomy control surface."""

from __future__ import annotations

import argparse
import asyncio
import copy
import dataclasses
import json
import os
import socket
import stat
import subprocess
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

import pytest

from control_plane.executive_autonomy import StatusEvidence
from ops.executive_os import autonomy_control as control


SHA = "c" * 40
NOW = datetime(2026, 8, 24, 12, 0, 0, tzinfo=UTC)
GATE_PATH = Path("/private/tmp/gate-b.json")


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

    # R17 B1: the CEO-submit operation domain is the SAME parser, three verbs,
    # each bounded to --expected-sha alone.
    assert vars(parser.parse_args(["ceo-submit-status", "--expected-sha", SHA])) == {
        "command": "ceo-submit-status",
        "expected_sha": SHA,
    }
    assert vars(parser.parse_args(["ceo-submit-arm", "--expected-sha", SHA])) == {
        "command": "ceo-submit-arm",
        "expected_sha": SHA,
    }
    assert vars(parser.parse_args(["ceo-submit-disarm", "--expected-sha", SHA])) == {
        "command": "ceo-submit-disarm",
        "expected_sha": SHA,
    }

    # The command set is EXACTLY the closed six: no seventh verb exists, and the
    # three legacy verbs are still present.
    subparser_actions = [
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ]
    assert len(subparser_actions) == 1
    assert set(subparser_actions[0].choices) == {
        "status",
        "arm",
        "disarm",
        "ceo-submit-status",
        "ceo-submit-arm",
        "ceo-submit-disarm",
    }

    # A CEO verb carries no COO authority flag: the arm admission surface of the
    # legacy verb must not be reachable from the CEO domain.
    for coo_flag, value in (
        ("--gate-b-receipt", "/private/tmp/gate-b.json"),
        ("--expected-credential-kind", "device-auth"),
        ("--workspace-binding-class", "company-workspace-admin-attested"),
        ("--credential-expires-at", "2026-08-25T12:00:00Z"),
    ):
        with pytest.raises(SystemExit):
            parser.parse_args(
                ["ceo-submit-arm", "--expected-sha", SHA, coo_flag, value]
            )

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

    for verb in ("ceo-submit-status", "ceo-submit-arm", "ceo-submit-disarm"):
        ceo_help = subparser_actions[0].choices[verb].format_help()
        for forbidden in (
            "--system-root",
            "--runtime-root",
            "--config-path",
            "--receipt-path",
            "--service-label",
            "--release-root",
            "--command-path",
        ):
            assert forbidden not in ceo_help


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
    assert "credential_rotation_interlock.py" in install

    production = (root / "ops/executive_os/autonomy_control.py").read_text(
        encoding="utf-8"
    )
    for digest in (
        control.CAPABILITY_POLICY_DIGEST,
        control.EXECUTION_PROFILE_DIGEST,
        control.NATIVE_HELPER_GRANT_DIGEST,
        control.SECURITY_CONFIG_DIGEST,
    ):
        assert digest not in production


def test_production_status_never_calls_an_invalid_present_receipt_unarmed(
    monkeypatch: pytest.MonkeyPatch,
):
    host = control.ProductionStatusHost()
    monkeypatch.setattr(host, "_require_host", lambda: None)
    monkeypatch.setattr(host, "_release_identity", lambda expected_sha: expected_sha)
    monkeypatch.setattr(host, "_transaction_present", lambda: False)
    monkeypatch.setattr(
        host,
        "_configs",
        lambda: (
            {
                "coo_autonomy_armed": False,
                "coo_operator_harness_armed": False,
            },
            {"operator_harness_armed": False},
            "1" * 64,
            "2" * 64,
            b"control",
            b"worker",
        ),
    )
    monkeypatch.setattr(
        host,
        "_receipt",
        lambda **_kwargs: (None, False, None, "receipt_invalid"),
    )
    monkeypatch.setattr(host, "_service_state", lambda _sha: ("STOPPED", True))
    snapshot = host.collect_status("a" * 40, now=NOW)
    assert snapshot.evidence.config_drift is True
    assert control.status_document(snapshot, now=NOW)["status"] == "CONFIG_DRIFT"


class FakeAdmissionHost:
    GATE_ORDER = (
        "install",
        "acceptance",
        "gate_b",
        "readiness",
        "configs",
        "runtime",
        "services",
        "uids",
        "transaction",
    )

    def __init__(self, fail_at=None):
        self.fail_at = fail_at
        self.calls = []
        self.config_writes = 0
        self.service_starts = 0
        self.login_calls = 0
        self.inference_calls = 0

    def _call(self, name):
        self.calls.append(name)
        if self.fail_at == name:
            raise control.ArmAdmissionError(f"{name}_gate_failed")

    def require_exact_install(self, expected_sha):
        self._call("install")
        return expected_sha

    def validate_acceptance(self, expected_sha):
        self._call("acceptance")
        return "3" * 64

    def validate_gate_b(self, path, expected_sha):
        self._call("gate_b")
        assert path == GATE_PATH
        return "4" * 64

    def validate_provider_readiness(self, request, *, now):
        self._call("readiness")
        return control.ReadinessEvidence(
            receipt_sha256="5" * 64,
            observed_at="2026-08-24T11:50:00Z",
            credential_expires_at=request.credential_expires_at,
            readiness_expires_at="2026-08-24T14:00:00Z",
        )

    def load_unarmed_configs(self, expected_sha):
        self._call("configs")
        return control.ConfigEvidence(
            control_sha256="6" * 64,
            worker_sha256="7" * 64,
            control={"coo_autonomy_armed": False, "coo_operator_harness_armed": False},
            worker={"operator_harness_armed": False},
        )

    def require_runtime_quiescent(self, config):
        self._call("runtime")

    def require_services_stopped(self):
        self._call("services")

    def require_service_uids_quiescent(self):
        self._call("uids")

    def require_transaction_absent(self):
        self._call("transaction")


def _arm_request(**overrides):
    values = {
        "expected_sha": SHA,
        "gate_b_receipt": GATE_PATH,
        "expected_credential_kind": "device-auth",
        "workspace_binding_class": "company-workspace-admin-attested",
        "credential_expires_at": "2026-08-25T12:00:00Z",
    }
    values.update(overrides)
    return control.ArmRequest(**values)


def test_arm_admission_proves_every_gate_once_in_fixed_order():
    host = FakeAdmissionHost()
    admission = control.evaluate_arm_admission(host, _arm_request(), now=NOW)

    assert host.calls == list(FakeAdmissionHost.GATE_ORDER)
    assert admission.expected_sha == SHA
    assert admission.acceptance_receipt_sha256 == "3" * 64
    assert admission.gate_b_receipt_sha256 == "4" * 64
    assert admission.readiness.receipt_sha256 == "5" * 64
    assert admission.configs.control_sha256 == "6" * 64
    assert admission.configs.worker_sha256 == "7" * 64
    assert admission.predicates == {
        "acceptance_passed": True,
        "configs_validated": True,
        "gate_b_passed": True,
        "provider_readiness_passed": True,
        "runtime_quiescent": True,
        "service_uids_quiescent": True,
    }
    assert host.config_writes == host.service_starts == 0
    assert host.login_calls == host.inference_calls == 0


@pytest.mark.parametrize("gate", FakeAdmissionHost.GATE_ORDER)
def test_every_admission_failure_stops_before_any_mutation_or_provider_effect(gate):
    host = FakeAdmissionHost(fail_at=gate)
    with pytest.raises(control.ArmAdmissionError) as raised:
        control.evaluate_arm_admission(host, _arm_request(), now=NOW)
    assert raised.value.code == f"{gate}_gate_failed"
    assert host.calls == list(FakeAdmissionHost.GATE_ORDER[: FakeAdmissionHost.GATE_ORDER.index(gate) + 1])
    assert host.config_writes == host.service_starts == 0
    assert host.login_calls == host.inference_calls == 0


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"passed": False}, "acceptance_not_passed"),
        ({"exact_origin_master_sha": "d" * 40}, "acceptance_sha_mismatch"),
        ({"detached_session_cleanup": "FAIL"}, "acceptance_predicate_failed"),
        ({"extra": "field"}, "acceptance_fields_mismatch"),
    ],
)
def test_acceptance_summary_is_exact_and_closed(changes, code):
    value = {
        "schema_version": "mastermind.executive_host_acceptance/v1",
        "passed": True,
        "observed_at": "2026-08-24T11:00:00Z",
        "exact_origin_master_sha": SHA,
        "release_root": f"/Library/Application Support/MastermindExecutive/releases/{SHA}",
        "control_uid": 450,
        "worker_uid": 451,
        "success_job_id": "JOB-001",
        "interrupted_requeued_job_id": "JOB-002",
        "detached_session_cleanup": "PASS",
        "terminal_assignment_sealing": "PASS",
        "lost_workspace_rotation_boundary": "PASS",
        "backup_restore": "PASS",
        "no_public_listener": "PASS",
        "credential_leakage_scan": "PASS",
        "financial_scheduler_activation": "NOT_REQUESTED_OR_TOUCHED",
    }
    value.update(changes)
    with pytest.raises(control.ArmAdmissionError) as raised:
        control.validate_acceptance_document(value, expected_sha=SHA)
    assert raised.value.code == code


def test_acceptance_summary_happy_path_returns_no_content():
    value = {
        "schema_version": "mastermind.executive_host_acceptance/v1",
        "passed": True,
        "observed_at": "2026-08-24T11:00:00Z",
        "exact_origin_master_sha": SHA,
        "release_root": f"/Library/Application Support/MastermindExecutive/releases/{SHA}",
        "control_uid": 450,
        "worker_uid": 451,
        "success_job_id": "JOB-001",
        "interrupted_requeued_job_id": "JOB-002",
        "detached_session_cleanup": "PASS",
        "terminal_assignment_sealing": "PASS",
        "lost_workspace_rotation_boundary": "PASS",
        "backup_restore": "PASS",
        "no_public_listener": "PASS",
        "credential_leakage_scan": "PASS",
        "financial_scheduler_activation": "NOT_REQUESTED_OR_TOUCHED",
    }
    assert control.validate_acceptance_document(value, expected_sha=SHA) is None


def _gate_b(**overrides):
    value = {
        "schema_version": "mastermind.executive_git_handoff_preflight/v1",
        "passed": True,
        "release_sha": SHA,
        "control": {},
        "worker": {},
        "workspace": {},
        "index_before_service_observation": {},
        "index_after_service_observation": {},
        "index_after_worker_preflight": {},
        "git": {},
        "persistent_config_unchanged": True,
        "worker_preflight_passed": True,
        "workspace_root_restored": True,
        "stimulus_used": True,
        "stimulus": {},
    }
    value.update(overrides)
    return value


def test_gate_b_reuses_canonical_validator_and_binds_exact_sha():
    control.validate_gate_b_document(_gate_b(), expected_sha=SHA)
    with pytest.raises(control.ArmAdmissionError) as raised:
        control.validate_gate_b_document(_gate_b(release_sha="d" * 40), expected_sha=SHA)
    assert raised.value.code == "gate_b_sha_mismatch"


@pytest.mark.parametrize(
    ("statuses", "code"),
    [
        (["COMPLETED", "FAILED", "CANCELLED", "LOST", "RATE_LIMITED"], None),
        (["CLAIMED"], "runtime_live_attempt"),
        (["RUNNING"], "runtime_live_attempt"),
        (["CHECKPOINTED"], "runtime_live_attempt"),
        (["CANCEL_REQUESTED"], "runtime_live_attempt"),
        (["EFFECT_UNKNOWN"], "runtime_attempt_status_unknown"),
    ],
)
def test_runtime_quiescence_classifier_refuses_every_live_or_unknown_attempt(statuses, code):
    if code is None:
        assert control.validate_runtime_attempt_statuses(statuses) is None
    else:
        with pytest.raises(control.ArmAdmissionError) as raised:
            control.validate_runtime_attempt_statuses(statuses)
        assert raised.value.code == code


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("workspace_binding_class", "personal", "workspace_binding_invalid"),
        ("credential_expires_at", "never", "credential_expiry_invalid"),
        ("credential_expires_at", "2026-08-24T12:00:00Z", "credential_expired"),
        ("expected_credential_kind", "operator-copy", "credential_kind_invalid"),
    ],
)
def test_arm_request_is_validated_before_the_first_host_gate(field, value, code):
    host = FakeAdmissionHost()
    with pytest.raises(control.ArmAdmissionError) as raised:
        control.evaluate_arm_admission(host, _arm_request(**{field: value}), now=NOW)
    assert raised.value.code == code
    assert host.calls == []


def test_production_admission_reuses_readiness_and_opens_runtime_read_only():
    source = (
        Path(__file__).resolve().parents[1]
        / "ops/executive_os/autonomy_control.py"
    ).read_text(encoding="utf-8")
    production = source.split("class ProductionArmHost", 1)[1]
    assert "provider_readiness.validate_receipt_file(" in production
    assert "Runtime.at(" in production
    assert "create=False" in production
    assert '["/usr/bin/pgrep", "-U", str(uid)]' in production
    for forbidden in (
        "provider_readiness.reserve",
        "provider_readiness._finalize",
        "provider_inference_canary",
        "codex login",
        "--device-auth",
        "--with-access-token",
        "ps -",
        "command=",
    ):
        assert forbidden not in production


def test_production_service_gate_stops_then_requires_both_launchdaemons_absent(monkeypatch):
    host = control.ProductionArmHost()
    monkeypatch.setattr(host, "_loaded", lambda label: False)
    host.require_services_stopped()

    loaded = {control.CONTROL_LABEL: True, control.WORKER_LABEL: True}
    stopped = []
    monkeypatch.setattr(host, "_loaded", lambda label: loaded[label])

    def stop():
        stopped.append(True)
        loaded[control.CONTROL_LABEL] = False
        loaded[control.WORKER_LABEL] = False

    monkeypatch.setattr(host, "_stop_services_for_admission", stop)
    host.require_services_stopped()
    assert stopped == [True]

    loaded[control.CONTROL_LABEL] = True
    monkeypatch.setattr(host, "_stop_services_for_admission", lambda: None)
    with pytest.raises(control.ArmAdmissionError) as raised:
        host.require_services_stopped()
    assert raised.value.code == "services_not_stopped"


def test_runtime_classifier_does_not_treat_empty_or_unknown_as_quiescent():
    with pytest.raises(control.ArmAdmissionError) as raised:
        control.validate_runtime_attempt_statuses([""])
    assert raised.value.code == "runtime_attempt_status_unknown"


class FakeTransactionHost(FakeAdmissionHost):
    PHASES = (
        "lock",
        "candidates",
        "validated",
        "worker",
        "control",
        "receipt",
        "started",
        "ready",
    )

    def __init__(self, fail_after=None, *, rollback_fails=False):
        super().__init__()
        self.fail_after = fail_after
        self.rollback_fails = rollback_fails
        self.marker = False
        self.services = "STOPPED"
        self.receipt = None
        self.transaction_calls = []
        self.control_config = {
            "schema_version": "control-v1",
            "proof_base_sha": SHA,
            "coo_autonomy_armed": False,
            "coo_operator_harness_armed": False,
            "preserved": {"alpha": 1},
        }
        self.worker_config = {
            "schema_version": "worker-v4",
            "operator_harness_armed": False,
            "preserved": ["beta"],
        }
        self.prior_control = None
        self.prior_worker = None
        self.last_request = None

    def _phase(self, name):
        self.transaction_calls.append(name)
        if self.fail_after == name:
            raise RuntimeError(f"fault after {name}")

    def existing_arm(self, request, *, now):
        if not self.control_config["coo_autonomy_armed"]:
            return None
        if self.last_request == request and self.receipt is not None:
            return control.TransactionResult(
                state="ARMED",
                status="ARMED_READY",
                transaction_id=self.receipt["transaction_id"],
                replayed=True,
            )
        raise control.ArmAdmissionError("changed_arm_evidence")

    def existing_disarm(self, expected_sha, *, now):
        if (
            not self.marker
            and self.control_config["coo_autonomy_armed"] is False
            and self.control_config["coo_operator_harness_armed"] is False
            and self.worker_config["operator_harness_armed"] is False
        ):
            return control.TransactionResult(
                state="DISARMED",
                status="UNARMED",
                transaction_id=(
                    self.receipt["transaction_id"] if self.receipt is not None else None
                ),
                replayed=True,
            )
        return None

    def load_unarmed_configs(self, expected_sha):
        self._call("configs")
        if self.control_config["coo_autonomy_armed"]:
            raise control.ArmAdmissionError("configs_not_unarmed")
        return control.ConfigEvidence(
            control_sha256=control.sha256_bytes(
                control.encode_config(self.control_config)
            ),
            worker_sha256=control.sha256_bytes(
                control.encode_config(self.worker_config)
            ),
            control=dict(self.control_config),
            worker=dict(self.worker_config),
            control_bytes=control.encode_config(self.control_config),
            worker_bytes=control.encode_config(self.worker_config),
        )

    def new_transaction_id(self):
        return "autonomy-deadbeefcafe"

    def begin_transaction(self, transaction):
        self.marker = True
        self.prior_control = dict(self.control_config)
        self.prior_worker = dict(self.worker_config)
        self._phase("lock")

    def write_candidates(self, transaction):
        self._phase("candidates")

    def validate_candidates(self, transaction):
        self._phase("validated")

    def replace_worker_config(self, transaction):
        self.worker_config = json.loads(transaction.candidates.worker_bytes)
        self._phase("worker")

    def replace_control_config(self, transaction):
        self.control_config = json.loads(transaction.candidates.control_bytes)
        self._phase("control")

    def write_autonomy_receipt(self, transaction, receipt):
        self.receipt = dict(receipt)
        self._phase("receipt")

    def start_services(self, expected_sha):
        self.services = "STARTING"
        self.service_starts += 1
        self._phase("started")

    def prove_services_ready(self, expected_sha):
        self.services = "READY"
        self._phase("ready")

    def complete_transaction(self, transaction):
        self.marker = False

    def stop_services(self, expected_sha):
        self.services = "STOPPED"

    def rollback_disarmed(self, transaction, receipt):
        if self.rollback_fails:
            raise RuntimeError("rollback fault")
        self.control_config = dict(self.prior_control)
        self.worker_config = dict(self.prior_worker)
        self.control_config["coo_autonomy_armed"] = False
        self.control_config["coo_operator_harness_armed"] = False
        self.worker_config["operator_harness_armed"] = False
        self.receipt = dict(receipt)
        self.marker = False

    def begin_disarm(self, expected_sha, transaction_id):
        self.marker = True
        self.prior_control = dict(self.control_config)
        self.prior_worker = dict(self.worker_config)
        self._phase("lock")
        return control.ConfigEvidence(
            control_sha256=control.sha256_bytes(control.encode_config(self.control_config)),
            worker_sha256=control.sha256_bytes(control.encode_config(self.worker_config)),
            control=dict(self.control_config),
            worker=dict(self.worker_config),
            control_bytes=control.encode_config(self.control_config),
            worker_bytes=control.encode_config(self.worker_config),
        )


def test_arm_transaction_changes_only_both_arm_bits_and_binds_one_receipt():
    host = FakeTransactionHost()
    request = _arm_request()
    before_control = json.loads(json.dumps(host.control_config))
    before_worker = json.loads(json.dumps(host.worker_config))

    result = control.execute_arm(host, request, now=NOW)

    assert result == control.TransactionResult(
        state="ARMED",
        status="ARMED_READY",
        transaction_id="autonomy-deadbeefcafe",
        replayed=False,
    )
    assert host.transaction_calls == list(FakeTransactionHost.PHASES)
    assert host.marker is False
    assert host.services == "READY"
    assert host.control_config == {
        **before_control,
        "coo_autonomy_armed": True,
        "coo_operator_harness_armed": True,
    }
    assert host.worker_config == {
        **before_worker,
        "operator_harness_armed": True,
    }
    assert host.receipt["state"] == "ARMED"
    assert host.receipt["control_config_sha256"] == control.sha256_bytes(
        control.encode_config(host.control_config)
    )
    assert host.receipt["worker_config_sha256"] == control.sha256_bytes(
        control.encode_config(host.worker_config)
    )
    from control_plane import executive_autonomy

    binding = executive_autonomy.validate_receipt_document(
        host.receipt,
        metadata=executive_autonomy.ReceiptMetadata(
            uid=0,
            gid=0,
            mode=0o444,
            nlink=1,
            is_regular=True,
            is_symlink=False,
            has_acl=False,
        ),
        expected=executive_autonomy.AutonomyExpectation(
            release_sha=SHA,
            control_config_sha256=host.receipt["control_config_sha256"],
            worker_config_sha256=host.receipt["worker_config_sha256"],
            provider_readiness_receipt_sha256="5" * 64,
            capability_policy_digest=control.CAPABILITY_POLICY_DIGEST,
            execution_profile_digest=control.EXECUTION_PROFILE_DIGEST,
            native_helper_grant_digest=control.NATIVE_HELPER_GRANT_DIGEST,
            security_config_digest=control.SECURITY_CONFIG_DIGEST,
        ),
        now=NOW,
    )
    assert binding.state == "ARMED"
    assert "token" not in json.dumps(host.receipt).lower()


@pytest.mark.parametrize("phase", FakeTransactionHost.PHASES)
def test_failure_after_every_durable_phase_rolls_back_to_both_false(phase):
    host = FakeTransactionHost(fail_after=phase)
    with pytest.raises(control.ArmTransactionError) as raised:
        control.execute_arm(host, _arm_request(), now=NOW)
    assert raised.value.code == "arm_rolled_back"
    assert host.control_config["coo_autonomy_armed"] is False
    assert host.control_config["coo_operator_harness_armed"] is False
    assert host.worker_config["operator_harness_armed"] is False
    assert host.receipt["state"] == "DISARMED"
    assert host.services == "STOPPED"
    assert host.marker is False


def test_concurrent_marker_race_never_rolls_back_a_foreign_transaction():
    host = FakeTransactionHost()

    def conflict(_transaction):
        raise control.ArmAdmissionError("transaction_incomplete")

    host.begin_transaction = conflict
    with pytest.raises(control.ArmAdmissionError) as raised:
        control.execute_arm(host, _arm_request(), now=NOW)
    assert raised.value.code == "transaction_incomplete"
    assert host.receipt is None
    assert host.marker is False
    assert host.control_config["coo_autonomy_armed"] is False
    assert host.worker_config["operator_harness_armed"] is False


def test_unproven_rollback_retains_marker_and_returns_effect_unknown():
    host = FakeTransactionHost(fail_after="control", rollback_fails=True)
    with pytest.raises(control.TransactionEffectUnknown) as raised:
        control.execute_arm(host, _arm_request(), now=NOW)
    assert raised.value.code == "effect_unknown"
    assert host.marker is True
    assert host.services == "STOPPED"


def test_repeated_identical_arm_replays_receipt_without_restart_or_rewrite():
    host = FakeTransactionHost()
    request = _arm_request()
    first = control.execute_arm(host, request, now=NOW)
    first_calls = list(host.transaction_calls)
    first_starts = host.service_starts
    host.last_request = request

    second = control.execute_arm(host, request, now=NOW + timedelta(minutes=1))
    assert first.replayed is False
    assert second.replayed is True
    assert host.transaction_calls == first_calls
    assert host.service_starts == first_starts


def test_disarm_is_shrink_only_and_leaves_services_stopped():
    host = FakeTransactionHost()
    request = _arm_request()
    control.execute_arm(host, request, now=NOW)
    host.fail_after = None
    host.transaction_calls.clear()

    result = control.execute_disarm(host, SHA, now=NOW + timedelta(minutes=1))

    assert result.state == "DISARMED"
    assert result.status == "UNARMED"
    assert host.control_config["coo_autonomy_armed"] is False
    assert host.control_config["coo_operator_harness_armed"] is False
    assert host.worker_config["operator_harness_armed"] is False
    assert host.receipt["state"] == "DISARMED"
    assert host.receipt["expected_credential_kind"] == "none"
    assert host.services == "STOPPED"
    assert host.marker is False


def test_repeated_disarm_is_a_read_only_replay():
    host = FakeTransactionHost()
    first = control.execute_disarm(host, SHA, now=NOW)
    assert first.replayed is True
    assert host.transaction_calls == []
    assert host.receipt is None

    request = _arm_request()
    control.execute_arm(host, request, now=NOW)
    control.execute_disarm(host, SHA, now=NOW + timedelta(minutes=1))
    calls = list(host.transaction_calls)
    second = control.execute_disarm(host, SHA, now=NOW + timedelta(minutes=2))
    assert second.replayed is True
    assert host.transaction_calls == calls


def test_main_arm_and_disarm_emit_closed_transaction_documents(capsys):
    host = FakeTransactionHost()
    arm_result = control.main(
        [
            "arm",
            "--expected-sha",
            SHA,
            "--gate-b-receipt",
            str(GATE_PATH),
            "--expected-credential-kind",
            "device-auth",
            "--workspace-binding-class",
            "company-workspace-admin-attested",
            "--credential-expires-at",
            "2026-08-25T12:00:00Z",
        ],
        host=host,
        now=lambda: NOW,
    )
    assert arm_result == 0
    armed = json.loads(capsys.readouterr().out)
    assert armed == {
        "code": "armed",
        "replayed": False,
        "schema_version": control.OPERATION_SCHEMA_VERSION,
        "state": "ARMED",
        "status": "ARMED_READY",
        "transaction_id": "autonomy-deadbeefcafe",
    }

    host.fail_after = None
    host.transaction_calls.clear()
    disarm_result = control.main(
        ["disarm", "--expected-sha", SHA], host=host, now=lambda: NOW
    )
    assert disarm_result == 0
    disarmed = json.loads(capsys.readouterr().out)
    assert disarmed["code"] == "disarmed"
    assert disarmed["state"] == "DISARMED"
    assert disarmed["status"] == "UNARMED"


def test_main_arm_rollback_is_closed_nonzero_without_traceback(capsys):
    host = FakeTransactionHost(fail_after="control")
    result = control.main(
        [
            "arm",
            "--expected-sha",
            SHA,
            "--gate-b-receipt",
            str(GATE_PATH),
            "--expected-credential-kind",
            "device-auth",
            "--workspace-binding-class",
            "company-workspace-admin-attested",
            "--credential-expires-at",
            "2026-08-25T12:00:00Z",
        ],
        host=host,
        now=lambda: NOW,
    )
    captured = capsys.readouterr()
    assert result == 2
    document = json.loads(captured.out)
    assert document == {
        "code": "arm_rolled_back",
        "replayed": False,
        "schema_version": control.OPERATION_SCHEMA_VERSION,
        "state": "DISARMED",
        "status": "UNARMED",
        "transaction_id": None,
    }
    assert "Traceback" not in captured.out + captured.err


def test_transaction_order_and_static_safety_fences_are_structural():
    source = (
        Path(__file__).resolve().parents[1]
        / "ops/executive_os/autonomy_control.py"
    ).read_text(encoding="utf-8")
    execute = source.split("def execute_arm(", 1)[1].split("def execute_disarm(", 1)[0]
    assert execute.index("host.replace_worker_config") < execute.index(
        "host.replace_control_config"
    ) < execute.index("host.write_autonomy_receipt") < execute.index(
        "host.start_services"
    ) < execute.index("host.prove_services_ready") < execute.index(
        "host.complete_transaction"
    )
    assert execute.index("host.stop_services") < execute.index(
        "host.rollback_disarmed"
    )

    production = source.split("class ProductionTransactionHost", 1)[1]
    assert "os.mkdir(AUTONOMY_TRANSACTION, 0o700)" in production
    assert "os.fsync(" in source
    assert "os.replace(" in source
    assert "prior-control.json" in production
    assert "prior-worker.json" in production
    assert ".autonomy-control-" in production
    assert ".autonomy-worker-" in production
    for forbidden in (
        "rm -rf",
        "rmtree(",
        "eval(",
        "shell=True",
        "retry_arm",
        "auto_failover",
    ):
        assert forbidden not in production


CEO_SUBMIT_CLOSED_FIELDS = frozenset(
    {
        "release_sha",
        "installed_sha",
        "ceo_submit_armed",
        "ceo_ingress_app_peer_uid",
        "app_peer_user",
        "ceo_ingress_app_armed",
        "ceo_ingress_peer_uid",
        "ceo_ingress_socket_path",
        "ceo_ingress_launchd_socket_name",
        "ceo_ingress_app_macro_root",
        "app_binding_valid",
        "app_acl_valid",
        "app_topology_valid",
        "coo_autonomy_armed",
        "coo_operator_harness_armed",
        "worker_operator_harness_armed",
        "worker_config_sha256",
        "transaction_id",
    }
)
CEO_SUBMIT_APP_MACRO_ROOT = (
    "/Library/Application Support/MastermindExecutive/macro-sources/" + SHA
)


class FakeCeoSubmitHost:
    """CEO-submit arm host double: one serialized transaction, no provider surface."""

    # R80: the CEO-submit ARM/DISARM readiness stage is now the CEO-admission
    # proof (fixed control label + probe ok + AWAITING_CANARY, on the fixed
    # control socket) -- NOT the COO/global READY poll the old "ready" phase
    # named.  The phase string is renamed accordingly.
    CEO_PHASES = (
        "lock",
        "candidates",
        "validated",
        "control",
        "receipt",
        "reconciled",
        "admission_bound",
    )
    CEO_GATES = ("root", "install", "binding", "configs", "separation", "transaction")
    GATE_FAILURES = {
        "root": ("host", "privilege_required"),
        "install": ("admission", "release_identity_mismatch"),
        "binding": ("admission", "app_binding_invalid"),
        "configs": ("admission", "ceo_submit_already_armed"),
        "separation": ("admission", "ceo_ingress_separation_invalid"),
        "transaction": ("admission", "ceo_submit_transaction_incomplete"),
    }

    def __init__(
        self,
        fail_at=None,
        fail_after=None,
        *,
        rollback_fails=False,
        uid=0,
        incomplete_marker_operation=None,
        safe_coexistence=False,
    ):
        self.fail_at = fail_at
        self.fail_after = fail_after
        self.rollback_fails = rollback_fails
        self.uid = uid
        self.incomplete_marker_operation = incomplete_marker_operation
        self.safe_coexistence = safe_coexistence
        self.calls = []
        self.phases = []
        self.operations = []
        self.marker = False
        self.receipt = None
        self.rollback_receipt = None
        self.last_transaction = None
        self.control_writes = 0
        self.worker_writes = 0
        self.worker_replace_calls = 0
        self.receipt_writes = 0
        self.reconcile_calls = 0
        self.admission_bound_calls = 0
        self.installed_sha = SHA
        self.binding_overrides = {}
        self.separation_overrides = {}
        self.control_config = {
            "schema_version": "mastermind.executive_control_config/v1",
            "proof_base_sha": SHA,
            "ceo_submit_armed": False,
            # R68: the governed App composition H3 arms from requires the
            # UID458 App transport ``ceo_ingress_app_armed`` to be True; ARM
            # gates on this being strictly True before any write.  The fake's
            # default is therefore True (the composed fixed gateway state)
            # so most ARM-path tests reach the postimage write stage.
            "ceo_ingress_app_armed": True,
            "ceo_ingress_app_peer_uid": 458,
            "ceo_ingress_peer_uid": 452,
            "ceo_ingress_socket_path": "/var/run/mastermind-executive/ceo-ingress.sock",
            "ceo_ingress_launchd_socket_name": "CeoIngress",
            "ceo_ingress_app_macro_root": CEO_SUBMIT_APP_MACRO_ROOT,
            "coo_autonomy_armed": False,
            "coo_operator_harness_armed": False,
            "coo_tick_interval_seconds": 15.0,
            "coo_model_alias": "coo.sealed",
            "preserved": {"alpha": 1},
        }
        self.worker_config = {
            "schema_version": "mastermind.executive_worker_config/v1",
            "operator_harness_armed": False,
            "preserved": ["beta"],
        }

    def _call(self, name):
        self.calls.append(name)
        if self.fail_at == name:
            kind, code = self.GATE_FAILURES[name]
            if kind == "host":
                raise control.HostControlError(code)
            raise control.CeoSubmitAdmissionError(code)

    def _phase(self, name):
        self.phases.append(name)
        if self.fail_after == name:
            raise RuntimeError(f"fault after {name}")

    def effective_uid(self):
        self._call("root")
        return self.uid

    def require_exact_install(self, expected_sha):
        self._call("install")
        return self.installed_sha

    def load_ceo_submit_configs(self, expected_sha):
        self._call("configs")
        return control.ConfigEvidence(
            control_sha256=control.sha256_bytes(
                control.encode_config(self.control_config)
            ),
            worker_sha256=control.sha256_bytes(
                control.encode_config(self.worker_config)
            ),
            control=copy.deepcopy(self.control_config),
            worker=copy.deepcopy(self.worker_config),
            control_bytes=control.encode_config(self.control_config),
            worker_bytes=control.encode_config(self.worker_config),
        )

    def executive_app_binding(self):
        self._call("binding")
        # R68: the R76 six-fact ARM-side check requires the live binding
        # match the control config on every fact.  The fake's defaults
        # therefore match the control config's defaults so the standard
        # ARM tests reach the postimage write stage.  Per-test overrides
        # remain authoritative but a binding-only override is ABSORBED by
        # the next control/binding sync -- drift tests must flip BOTH the
        # live override AND its control counterpart.
        values = {
            "present": True,
            "app_peer_uid": self.control_config.get(
                "ceo_ingress_app_peer_uid", 458
            ),
            "app_peer_user": control.EXECUTIVE_APP_USER,
            "app_armed": self.control_config.get("ceo_ingress_app_armed", True),
            "app_macro_root": self.control_config.get(
                "ceo_ingress_app_macro_root", CEO_SUBMIT_APP_MACRO_ROOT
            ),
            "ingress_peer_uid": self.control_config.get(
                "ceo_ingress_peer_uid", 452
            ),
            "ingress_socket_path": self.control_config.get(
                "ceo_ingress_socket_path",
                "/var/run/mastermind-executive/ceo-ingress.sock",
            ),
            "launchd_socket_name": self.control_config.get(
                "ceo_ingress_launchd_socket_name", "CeoIngress"
            ),
            "binding_valid": True,
            "acl_valid": True,
            "topology_valid": True,
        }
        values.update(self.binding_overrides)
        return control.ExecutiveAppBinding(**values)

    def ceo_submit_separation(self, configs):
        self._call("separation")
        values = {
            "ceo_ingress_app_armed": configs.control["ceo_ingress_app_armed"],
            "ceo_ingress_app_peer_uid": configs.control["ceo_ingress_app_peer_uid"],
            "ceo_ingress_peer_uid": configs.control["ceo_ingress_peer_uid"],
            "coo_autonomy_armed": configs.control["coo_autonomy_armed"],
            "coo_operator_harness_armed": configs.control["coo_operator_harness_armed"],
            "worker_operator_harness_armed": configs.worker["operator_harness_armed"],
        }
        values.update(self.separation_overrides)
        return control.CeoSubmitSeparation(**values)

    def require_transaction_absent(self):
        self._call("transaction")
        if self.marker or self.incomplete_marker_operation is not None:
            raise control.CeoSubmitAdmissionError("ceo_submit_transaction_incomplete")

    def incomplete_transaction_operation(self):
        # A read-only marker probe, deliberately NOT recorded in ``calls``: it is
        # not an admission gate, it is the R9 stickiness discriminator.
        return self.incomplete_marker_operation

    def proves_safe_coexistence(self, configs):
        return self.safe_coexistence

    def existing_ceo_submit_receipt(self):
        return self.receipt

    @property
    def ceo_submit_receipt(self):
        """The sealed-receipt store (``receipt`` is the packet-1 spelling)."""

        return self.receipt

    def reset_ledgers(self):
        """Clear the observation ledgers so a second operation reads cleanly."""

        self.calls.clear()
        self.phases.clear()
        self.operations.clear()
        self.control_writes = 0
        self.worker_writes = 0
        self.worker_replace_calls = 0
        self.receipt_writes = 0
        self.reconcile_calls = 0
        self.admission_bound_calls = 0

    def new_transaction_id(self):
        return "autonomy-feedfacec0de"

    def begin_ceo_submit_transaction(self, transaction, *, operation):
        self.operations.append(operation)
        self.last_transaction = transaction
        self.marker = True
        self._phase("lock")

    def write_candidates(self, transaction):
        self.last_transaction = transaction
        self._phase("candidates")

    def validate_candidates(self, transaction):
        self._phase("validated")

    def replace_control_config(self, transaction):
        self.control_config = json.loads(
            transaction.candidates.control_bytes.decode("utf-8")
        )
        self.control_writes += 1
        self._phase("control")

    def replace_worker_config(self, transaction):
        self.worker_replace_calls += 1
        raise AssertionError("CEO-submit ARM must never replace the worker config")

    def write_ceo_submit_receipt(self, transaction, receipt):
        self.receipt = json.loads(control._encoded_json(receipt).decode("utf-8"))
        self.receipt_writes += 1
        self._phase("receipt")

    def reconcile_control_service(self, expected_sha):
        self.reconcile_calls += 1
        self._phase("reconciled")

    def prove_control_admission_bound(
        self, expected_sha, *, candidate_config_digest
    ):
        # R80: rename matches the production protocol method and the new
        # fixed-arity signature.  The fake records every call (default
        # ADMITTED) regardless of the digest so it stays a pure witness.
        self.admission_bound_calls += 1
        self._phase("admission_bound")

    def complete_transaction(self, transaction):
        self.marker = False

    def rollback_ceo_submit(self, transaction, receipt):
        if self.rollback_fails:
            raise RuntimeError("rollback refused")
        self.rollback_receipt = json.loads(control._encoded_json(receipt).decode("utf-8"))
        self.control_config = json.loads(
            transaction.candidates.control_bytes.decode("utf-8")
        )
        self.marker = False


def _ceo_submit_request(**overrides):
    values = {"expected_sha": SHA}
    values.update(overrides)
    return control.CeoSubmitRequest(**values)


@pytest.mark.parametrize(
    ("uid", "admitted"), [(501, False), (1, False), (-1, False), (0, True)]
)
def test_ceo_submit_arm_refuses_every_non_root_effective_uid(uid, admitted):
    host = FakeCeoSubmitHost(uid=uid)
    before = copy.deepcopy(host.control_config)

    if admitted:
        result = control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)
        assert result.status == "CEO_SUBMIT_ARMED"
    else:
        with pytest.raises(control.HostControlError) as raised:
            control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)
        assert raised.value.code == "privilege_required"
        assert host.calls == ["root"]
        assert host.phases == []
        assert host.marker is False
        assert host.control_config == before

    assert control.require_root_privilege(0) is None
    if not admitted:
        with pytest.raises(control.HostControlError) as gate:
            control.require_root_privilege(uid)
        assert gate.value.code == "privilege_required"
    for non_root in (1, -1, 501):
        with pytest.raises(control.HostControlError):
            control.require_root_privilege(non_root)

    source = Path(control.__file__).read_text(encoding="utf-8")
    body = source.split("def require_root_privilege(", 1)[1].split("\ndef ", 1)[0]
    assert "geteuid" not in body
    assert "os." not in body


def test_ceo_submit_arm_uses_the_one_global_transaction_owner_and_no_second_lock():
    source = Path(control.__file__).read_text(encoding="utf-8")
    assert "ceo-submit-transaction.lock" not in source
    assert control.AUTONOMY_TRANSACTION == control.CONFIG_ROOT / "autonomy-transaction.lock"
    lock_paths = {
        name
        for name, value in vars(control).items()
        if isinstance(value, Path) and "lock" in value.name.lower()
    }
    assert lock_paths == {"AUTONOMY_TRANSACTION"}
    assert source.count("os.mkdir(") == 1

    production = source.split("class ProductionCeoSubmitHost", 1)[1]
    begin = production.split("def begin_ceo_submit_transaction", 1)[1].split(
        "\n    def ", 1
    )[0]
    assert "AUTONOMY_TRANSACTION" in begin
    assert "_create_marker" in begin

    host = FakeCeoSubmitHost()
    control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)
    assert host.operations == ["CEO_SUBMIT_ARM"]
    assert host.phases[0] == "lock"
    assert host.calls[0] == "root"
    assert host.marker is False


def test_ceo_submit_arm_mutates_only_control_json_and_leaves_worker_byte_identical():
    host = FakeCeoSubmitHost()
    before_worker = control.encode_config(host.worker_config)
    before_sha = control.sha256_bytes(before_worker)

    control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)

    after_worker = control.encode_config(host.worker_config)
    assert after_worker == before_worker
    assert control.sha256_bytes(after_worker) == before_sha
    assert host.worker_writes == 0
    assert host.worker_replace_calls == 0
    assert host.control_writes == 1
    assert host.last_transaction.candidates.worker_bytes == before_worker
    assert host.last_transaction.candidates.worker_sha256 == before_sha

    source = Path(control.__file__).read_text(encoding="utf-8")
    arm = source.split("def execute_ceo_submit_arm(", 1)[1].split("\ndef ", 1)[0]
    assert "host.replace_control_config" in arm
    assert "replace_worker_config" not in arm
    production = source.split("class ProductionCeoSubmitHost", 1)[1]
    fence = production.split("def replace_worker_config", 1)[1].split(
        "\n    def ", 1
    )[0]
    assert "raise TransactionEffectUnknown()" in fence


def test_ceo_submit_candidate_passes_the_installed_worker_bytes_through_without_re_encoding():
    """R9: the candidate carries the INSTALLED worker bytes, never a re-derivation.

    The sibling byte-identity tests compare ``encode_config(...)`` on both sides,
    so a refactor to ``worker_bytes=encode_config(dict(configs.worker))`` stayed
    green.  Here the installed worker document is deliberately NON-CANONICAL —
    insertion key order and a different indent — so canonicalizing it is visible.
    ``candidate.worker`` is asserted by VALUE (``==``), not object identity: R9
    constrains the bytes, and this module never promised the same dict object.
    """

    host = FakeCeoSubmitHost()
    worker = dict(host.worker_config)
    installed_worker_bytes = (
        json.dumps(worker, sort_keys=False, indent=4, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    # The installed bytes really are that document, and they are NOT the canonical
    # encoding of it — otherwise this test could not discriminate.
    assert json.loads(installed_worker_bytes.decode("utf-8")) == worker
    assert installed_worker_bytes != control.encode_config(worker)

    configs = control.ConfigEvidence(
        control_sha256=control.sha256_bytes(
            control.encode_config(host.control_config)
        ),
        worker_sha256=control.sha256_bytes(installed_worker_bytes),
        control=dict(host.control_config),
        worker=worker,
        control_bytes=control.encode_config(host.control_config),
        worker_bytes=installed_worker_bytes,
    )

    for armed in (True, False):
        candidate = control.derive_ceo_submit_candidate(configs, armed=armed)
        # Byte equality with the INPUT bytes, and provably not a re-encode.
        assert candidate.worker_bytes == installed_worker_bytes
        assert candidate.worker_bytes != control.encode_config(worker)
        assert candidate.worker_sha256 == configs.worker_sha256
        assert candidate.worker_sha256 == control.sha256_bytes(
            installed_worker_bytes
        )
        assert candidate.worker == configs.worker
        assert candidate.control["ceo_submit_armed"] is armed
        assert candidate.control_bytes == control.encode_config(
            {**host.control_config, "ceo_submit_armed": armed}
        )


def test_ceo_submit_arm_changes_only_the_ceo_submit_flag_in_control():
    host = FakeCeoSubmitHost()
    before = copy.deepcopy(host.control_config)

    control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)

    assert set(host.control_config) == set(before)
    assert host.control_config == {**before, "ceo_submit_armed": True}
    changed = {
        key for key in before if before[key] != host.control_config[key]
    }
    assert changed == {"ceo_submit_armed"}

    drift = FakeCeoSubmitHost()
    drift.control_config["ceo_submit_armed"] = "yes"
    with pytest.raises(control.CeoSubmitAdmissionError) as raised:
        control.execute_ceo_submit_arm(drift, _ceo_submit_request(), now=NOW)
    assert raised.value.code == "ceo_submit_config_schema_drift"
    assert drift.phases == []
    assert drift.control_config["ceo_submit_armed"] == "yes"
    assert drift.control_writes == 0


@pytest.mark.parametrize("gate", FakeCeoSubmitHost.CEO_GATES)
def test_ceo_submit_arm_gate_order_is_fixed_and_every_gate_refuses_before_any_write(gate):
    host = FakeCeoSubmitHost(fail_at=gate)
    before_control = copy.deepcopy(host.control_config)
    before_worker = copy.deepcopy(host.worker_config)
    expected_kind, expected_code = FakeCeoSubmitHost.GATE_FAILURES[gate]
    error = (
        control.HostControlError
        if expected_kind == "host"
        else control.CeoSubmitAdmissionError
    )

    with pytest.raises(error) as raised:
        control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)

    assert raised.value.code == expected_code
    index = list(FakeCeoSubmitHost.CEO_GATES).index(gate) + 1
    assert host.calls == list(FakeCeoSubmitHost.CEO_GATES[:index])
    assert host.phases == []
    assert host.marker is False
    assert host.control_config == before_control
    assert host.worker_config == before_worker
    assert host.control_writes == 0
    assert host.worker_writes == 0
    assert host.receipt is None


def test_ceo_submit_arm_refuses_a_stale_or_mismatched_release_before_mutation():
    host = FakeCeoSubmitHost()
    host.installed_sha = "d" * 40
    before = copy.deepcopy(host.control_config)
    with pytest.raises(control.CeoSubmitAdmissionError) as raised:
        control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)
    assert raised.value.code == "release_identity_mismatch"
    assert host.calls == ["root", "install"]
    assert host.phases == []
    assert host.marker is False
    assert host.control_config == before
    assert host.control_writes == 0

    for bad_sha in ("", "abc", SHA.upper(), "f" * 39, "g" * 40):
        stale = FakeCeoSubmitHost()
        with pytest.raises(control.CeoSubmitAdmissionError) as bad:
            control.execute_ceo_submit_arm(
                stale, _ceo_submit_request(expected_sha=bad_sha), now=NOW
            )
        assert bad.value.code == "release_identity_mismatch"
        assert stale.calls == ["root"]
        assert stale.phases == []
        assert stale.control_writes == 0


@pytest.mark.parametrize(
    ("overrides", "code", "gates"),
    [
        ({"present": False}, "app_binding_absent", 3),
        ({"app_peer_user": "someone_else"}, "app_peer_invalid", 3),
        ({"binding_valid": False}, "app_binding_invalid", 3),
        ({"acl_valid": False}, "app_acl_invalid", 3),
        ({"topology_valid": False}, "app_topology_invalid", 3),
        # A host-observed App peer that disagrees with the config's declared App
        # peer is no longer a source-literal comparison at the binding gate: it
        # is refused by the gate-5 structural separation invariant (D8/R9).
        ({"app_peer_uid": 459}, "ceo_ingress_separation_invalid", 5),
    ],
)
def test_ceo_submit_arm_refuses_invalid_app_peer_binding_acl_or_topology(
    overrides, code, gates
):
    host = FakeCeoSubmitHost()
    host.binding_overrides = overrides
    before_control = copy.deepcopy(host.control_config)
    before_worker = copy.deepcopy(host.worker_config)

    with pytest.raises(control.CeoSubmitAdmissionError) as raised:
        control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)

    assert raised.value.code == code
    assert host.calls == list(FakeCeoSubmitHost.CEO_GATES[:gates])
    assert host.phases == []
    assert host.marker is False
    assert host.control_config == before_control
    assert host.worker_config == before_worker
    assert host.control_writes == 0


@pytest.mark.parametrize(
    ("config_key", "config_value", "binding_app_uid", "code"),
    [
        ("ceo_submit_armed", True, None, "ceo_submit_already_armed"),
        # R68: the UID458 App transport refusal flipped direction -- a False
        # ``ceo_ingress_app_armed`` (or non-boolean schema drift) now refuses
        # ARM with the typed pre-write ``ceo_ingress_app_unarmed`` code.
        ("ceo_ingress_app_armed", False, None, "ceo_ingress_app_unarmed"),
        # EQUAL ingress peers: the separation R9 requires is broken.
        ("ceo_ingress_peer_uid", 458, None, "ceo_ingress_separation_invalid"),
        ("ceo_ingress_app_peer_uid", 452, 452, "ceo_ingress_separation_invalid"),
        # DISTINCT peers, but the config App peer is not the host-observed one.
        # R9 + the sync host: peer identities are CONFIG facts (no source
        # literal), so the structural separation gate fires when the live
        # binding disagrees with the config -- that disagreement is forced
        # by overriding ``app_peer_uid`` while the config keeps its declared
        # value, the only shape the gate can refuse.
        ("ceo_ingress_app_peer_uid", 459, 458, "ceo_ingress_separation_invalid"),
        ("coo_autonomy_armed", True, None, "coo_autonomy_armed"),
        ("coo_operator_harness_armed", True, None, "coo_operator_harness_armed"),
    ],
)
def test_ceo_submit_arm_refuses_when_already_armed_ceo_ingress_unarmed_separation_broken_or_coo_armed(
    config_key, config_value, binding_app_uid, code
):
    host = FakeCeoSubmitHost()
    host.control_config[config_key] = config_value
    if binding_app_uid is not None:
        # Keep the EQUALITY case a pure equality case: the host-observed peer
        # tracks the config so only the structural invariant can refuse it.
        host.binding_overrides = {"app_peer_uid": binding_app_uid}
    before = copy.deepcopy(host.control_config)

    with pytest.raises(control.CeoSubmitAdmissionError) as raised:
        control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)

    assert raised.value.code == code
    assert host.phases == []
    assert host.marker is False
    assert host.control_config == before
    assert host.control_writes == 0

    worker_armed = FakeCeoSubmitHost()
    worker_armed.worker_config["operator_harness_armed"] = True
    before_worker = copy.deepcopy(worker_armed.worker_config)
    with pytest.raises(control.CeoSubmitAdmissionError) as worker_raised:
        control.execute_ceo_submit_arm(worker_armed, _ceo_submit_request(), now=NOW)
    assert worker_raised.value.code == "worker_operator_harness_armed"
    assert worker_armed.phases == []
    assert worker_armed.worker_config == before_worker
    assert worker_armed.control_writes == 0


def test_ceo_submit_arm_derives_peer_identities_from_config_not_from_source_literals():
    """R9 + D8: the ingress peer identities are CONFIG facts, never constants.

    The identity UIDs are pinned once, in the composed control config asserted by
    tests/test_ceo_submit_armed_composition.py.  This module must therefore expose
    no ``CEO_INGRESS_*_PEER_UID`` literals at all and must enforce the separation
    structurally: any two DISTINCT ints the installed host agrees with -- and no
    pair that violates the invariant -- decide admission.
    """

    assert not hasattr(control, "CEO_INGRESS_APP_PEER_UID")
    assert not hasattr(control, "CEO_INGRESS_PEER_UID")

    def _refusal(host):
        before = copy.deepcopy(host.control_config)
        with pytest.raises(control.CeoSubmitAdmissionError) as raised:
            control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)
        # No refusal may ever land after a durable phase or a write.
        assert host.phases == []
        assert host.operations == []
        assert host.marker is False
        assert host.control_writes == 0
        assert host.worker_writes == 0
        assert host.receipt is None
        assert host.control_config == before
        return raised.value.code

    # (1) EQUAL ingress uids destroy the C1-vs-App separation R9 requires, for
    #     the shipped pair and for any other pair alike.
    for equal_uid in (458, 452, 470):
        host = FakeCeoSubmitHost()
        host.control_config["ceo_ingress_app_peer_uid"] = equal_uid
        host.control_config["ceo_ingress_peer_uid"] = equal_uid
        host.binding_overrides = {
            "app_peer_uid": equal_uid,
            "ingress_peer_uid": equal_uid,
        }
        assert _refusal(host) == "ceo_ingress_separation_invalid"

    # (2) A peer identity that is not an int (bool included) is refused.
    for bad_value in ("458", True, 458.0, None):
        for key in ("ceo_ingress_app_peer_uid", "ceo_ingress_peer_uid"):
            host = FakeCeoSubmitHost()
            host.control_config[key] = bad_value
            assert _refusal(host) == "ceo_ingress_separation_invalid"

    # (3) The host-observed App peer must AGREE with the config's App peer.
    host = FakeCeoSubmitHost()
    host.binding_overrides = {"app_peer_uid": 459}
    assert _refusal(host) == "ceo_ingress_separation_invalid"

    # (4) The dedicated caller is still checked IDENTITY-BY-NAME at the binding
    #     gate, before the config is ever loaded.
    host = FakeCeoSubmitHost()
    host.binding_overrides = {"app_peer_user": "someone_else"}
    assert _refusal(host) == "app_peer_invalid"
    assert host.calls == list(FakeCeoSubmitHost.CEO_GATES[:3])

    # (5) Any two DISTINCT uids the host agrees with are ADMITTED, proving the
    #     module binds the invariant and not the magic numbers.
    for app_uid, ingress_uid in ((470, 471), (459, 458), (1001, 1002)):
        host = FakeCeoSubmitHost()
        host.control_config["ceo_ingress_app_peer_uid"] = app_uid
        host.control_config["ceo_ingress_peer_uid"] = ingress_uid
        host.binding_overrides = {
            "app_peer_uid": app_uid,
            "ingress_peer_uid": ingress_uid,
        }
        result = control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)
        assert result.status == "CEO_SUBMIT_ARMED"
        assert host.control_config["ceo_ingress_app_peer_uid"] == app_uid
        assert host.control_config["ceo_ingress_peer_uid"] == ingress_uid
        assert host.phases == list(FakeCeoSubmitHost.CEO_PHASES)


def test_ceo_submit_arm_requires_no_provider_readiness_gate_b_or_credential():
    import dataclasses

    assert {field.name for field in dataclasses.fields(control.CeoSubmitRequest)} == {
        "expected_sha"
    }

    host = FakeCeoSubmitHost()

    def _refuse(*_args, **_kwargs):
        raise AssertionError("provider readiness must never be consulted by CEO-submit")

    host.validate_provider_readiness = _refuse
    host.validate_gate_b = _refuse
    host.validate_acceptance = _refuse
    host.require_runtime_quiescent = _refuse
    host.require_services_stopped = _refuse
    host.require_service_uids_quiescent = _refuse

    admission = control.evaluate_ceo_submit_arm_admission(
        host, _ceo_submit_request(), now=NOW
    )
    assert admission.expected_sha == SHA
    assert admission.installed_sha == SHA
    assert host.calls == list(FakeCeoSubmitHost.CEO_GATES)

    result = control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)
    assert result.status == "CEO_SUBMIT_ARMED"
    assert "readiness" not in host.phases
    assert "gate_b" not in host.calls
    assert not hasattr(control.CeoSubmitRequest, "gate_b_receipt")
    assert not hasattr(control.CeoSubmitRequest, "credential_expires_at")


def test_ceo_submit_receipt_is_a_closed_projection_not_a_whole_file_digest():
    host = FakeCeoSubmitHost()
    control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)
    receipt = host.receipt

    assert set(receipt) == {
        "schema_version",
        "state",
        "operation",
        "projection",
        "projection_digest",
        "transaction_id",
        "observed_at",
        "tool_version",
    }
    assert receipt["schema_version"] == control.CEO_SUBMIT_RECEIPT_SCHEMA
    assert receipt["state"] == "CEO_SUBMIT_ARMED"
    assert receipt["operation"] == "CEO_SUBMIT_ARM"
    assert set(receipt["projection"]) == CEO_SUBMIT_CLOSED_FIELDS
    assert (
        control.ceo_submit_projection_digest(receipt["projection"])
        == receipt["projection_digest"]
    )
    assert receipt["projection_digest"] == control.sha256_bytes(
        control._encoded_json(receipt["projection"])
    )
    assert receipt["projection"]["ceo_submit_armed"] is True
    assert receipt["projection"]["transaction_id"] == receipt["transaction_id"]
    assert receipt["projection"]["release_sha"] == SHA
    assert not any(
        isinstance(value, (dict, list)) for value in receipt["projection"].values()
    )

    serialized = control._encoded_json(receipt).decode("utf-8")
    assert "control_document" not in receipt
    assert "coo_tick_interval_seconds" not in serialized
    assert "coo_model_alias" not in serialized
    assert "preserved" not in receipt["projection"]
    assert "schema_version" not in receipt["projection"]
    assert "proof_base_sha" not in receipt["projection"]
    assert str(receipt["projection"]["worker_operator_harness_armed"]) == "False"
    assert receipt["projection"]["worker_config_sha256"] == control.sha256_bytes(
        control.encode_config(host.worker_config)
    )
    assert "token" not in serialized.lower()


def test_writer_receipt_field_contract_and_document_parity():
    assert set(control._CEO_SUBMIT_RECEIPT_FIELDS) == {
        "schema_version",
        "state",
        "operation",
        "projection",
        "projection_digest",
        "transaction_id",
        "observed_at",
        "tool_version",
    }

    armed = _armed_ceo_submit_host()
    disarmed = _armed_ceo_submit_host()
    control.execute_ceo_submit_disarm(
        disarmed, _ceo_submit_request(), now=NOW + timedelta(minutes=1)
    )

    for host, armed_direction in ((armed, True), (disarmed, False)):
        receipt = host.receipt
        assert set(receipt) == control._CEO_SUBMIT_RECEIPT_FIELDS
        assert (
            control.validate_ceo_submit_receipt_document(
                receipt, armed=armed_direction
            )
            is True
        )


@pytest.mark.parametrize(
    "field",
    ["release_sha", "installed_sha"],
)
def test_receipt_document_requires_well_formed_release_and_installed_shas(field):
    host = _armed_ceo_submit_host()
    receipt = copy.deepcopy(host.receipt)
    for value in (None, "", "not-a-sha", "0" * 39, "g" * 40):
        receipt["projection"][field] = value
        _recompute_receipt_digest(receipt)
        assert (
            control.validate_ceo_submit_receipt_document(receipt, armed=True)
            is False
        )
        receipt = copy.deepcopy(host.receipt)


def test_receipt_document_requires_a_canonical_timestamp():
    host = _armed_ceo_submit_host()
    receipt = copy.deepcopy(host.receipt)
    for value in (
        None,
        1789548398,
        "2026-08-24 12:00:00Z",
        "2026-08-24T12:00:00+00:00",
        "2026-08-24t12:00:00z",
        "not-a-timestamp",
    ):
        receipt["observed_at"] = value
        assert control.validate_ceo_submit_receipt_document(receipt, armed=True) is False


def test_release_sha_rebinding_comes_from_expected_sha_not_the_receipt():
    host = _armed_ceo_submit_host()
    binding = host.executive_app_binding()
    worker = copy.deepcopy(host.worker_config)
    worker_sha = control.sha256_bytes(control.encode_config(worker))
    receipt = copy.deepcopy(host.receipt)
    receipt["projection"]["release_sha"] = "d" * 40
    _recompute_receipt_digest(receipt)

    assert control.validate_ceo_submit_receipt_document(receipt, armed=True) is True
    assert (
        control.ceo_submit_sink_eligible(
            control_config=host.control_config,
            worker_config=worker,
            worker_config_sha256=worker_sha,
            receipt=receipt,
            binding=binding,
            expected_sha=SHA,
            installed_sha=SHA,
        )
        is False
    )


def test_sink_eligibility_requires_a_present_live_binding():
    host = _armed_ceo_submit_host()
    binding = dataclasses.replace(
        host.executive_app_binding(), present=False, app_peer_uid=-1
    )

    assert (
        control.ceo_submit_sink_eligible(
            control_config=host.control_config,
            worker_config=host.worker_config,
            worker_config_sha256=control.sha256_bytes(
                control.encode_config(host.worker_config)
            ),
            receipt=host.receipt,
            binding=binding,
            expected_sha=SHA,
            installed_sha=SHA,
        )
        is False
    )


def test_writer_rejects_its_own_receipt_if_the_canonical_validator_refuses_it(monkeypatch):
    host = FakeCeoSubmitHost()
    configs = host.load_ceo_submit_configs(SHA)
    admission = control.evaluate_ceo_submit_arm_admission(
        host, control.CeoSubmitRequest(expected_sha=SHA), now=NOW
    )
    transaction = control.TransactionContext(
        transaction_id=host.new_transaction_id(),
        expected_sha=SHA,
        prior_configs=configs,
        candidates=control.derive_ceo_submit_candidate(configs, armed=True),
        admission=None,
    )
    monkeypatch.setattr(
        control,
        "validate_ceo_submit_receipt_document",
        lambda *_args, **_kwargs: False,
    )
    with pytest.raises(control.CeoSubmitAdmissionError) as raised:
        control.build_ceo_submit_receipt(transaction, admission, armed=True, now=NOW)
    assert raised.value.code == "ceo_submit_config_schema_drift"


def _sealed_ceo_submit_evidence():
    host = _armed_ceo_submit_host()
    binding = host.executive_app_binding()
    worker_config = copy.deepcopy(host.worker_config)
    worker_config_sha256 = control.sha256_bytes(control.encode_config(worker_config))
    return host, binding, worker_config, worker_config_sha256


def _direct_ceo_submit_sink_eligible(
    host,
    binding,
    worker_config,
    worker_config_sha256,
    receipt,
    *,
    installed_sha=SHA,
):
    return control.ceo_submit_sink_eligible(
        control_config=host.control_config,
        worker_config=worker_config,
        worker_config_sha256=worker_config_sha256,
        receipt=receipt,
        binding=binding,
        expected_sha=SHA,
        installed_sha=installed_sha,
    )


def _recompute_receipt_digest(receipt):
    receipt["projection_digest"] = control.ceo_submit_projection_digest(
        receipt["projection"]
    )


@pytest.mark.parametrize("field", control._CEO_SUBMIT_RECEIPT_FIELDS)
def test_missing_top_level_field_is_refused_at_every_level(field, capsys):
    host, binding, worker, worker_sha = _sealed_ceo_submit_evidence()
    receipt = copy.deepcopy(host.receipt)
    del receipt[field]

    assert control.validate_ceo_submit_receipt_document(receipt, armed=True) is False
    assert (
        _direct_ceo_submit_sink_eligible(
            host, binding, worker, worker_sha, receipt
        )
        is False
    )
    host.receipt = receipt
    host.reset_ledgers()
    status = control.evaluate_ceo_submit_status(host, _ceo_submit_request())
    assert status.state == "CEO_SUBMIT_ARMED_UNBOUND"
    assert host.control_writes == host.worker_writes == host.receipt_writes == 0
    assert host.marker is False
    assert host.phases == []

    exit_code = control.main(
        ["ceo-submit-status", "--expected-sha", SHA], host=host, now=lambda: NOW
    )
    document = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert document["code"] == "ceo_submit_armed_unbound"
    assert document["state"] == "CEO_SUBMIT_ARMED_UNBOUND"
    assert host.control_writes == host.worker_writes == host.receipt_writes == 0
    assert host.marker is False
    assert host.phases == []


@pytest.mark.parametrize(
    "case",
    [
        "outer_transaction_mismatch",
        "outer_transaction_missing",
        "outer_transaction_empty",
        "outer_transaction_nonstring",
        "outer_transaction_malformed",
        "projection_transaction_recomputed",
        "installed_sha_recomputed",
        "release_sha_recomputed",
        "observed_at_invalid",
        "observed_at_noncanonical",
        "observed_at_missing",
        "observed_at_nonstring",
        "tool_version_wrong",
        "tool_version_missing",
        "extra_top_level_field",
        "renamed_top_level_field",
        "wrong_schema_version",
        "wrong_state",
        "wrong_operation",
        "state_operation_mismatch",
        "projection_nonobject",
        "receipt_nonobject",
        "projection_field_missing",
        "projection_field_extra",
        "projection_digest_wrong",
        "projection_digest_wrong_type",
        "projection_digest_missing",
    ],
)
def test_malformed_receipt_is_refused_at_every_level(case, capsys):
    host, binding, worker, worker_sha = _sealed_ceo_submit_evidence()
    receipt = copy.deepcopy(host.receipt)
    expected_transaction = receipt["transaction_id"]

    if case == "outer_transaction_mismatch":
        receipt["transaction_id"] = "autonomy-0123456789ab"
    elif case == "outer_transaction_missing":
        del receipt["transaction_id"]
    elif case == "outer_transaction_empty":
        receipt["transaction_id"] = ""
    elif case == "outer_transaction_nonstring":
        receipt["transaction_id"] = 123
    elif case == "outer_transaction_malformed":
        receipt["transaction_id"] = "autonomy-not-a-hex-id"
    elif case == "projection_transaction_recomputed":
        receipt["projection"]["transaction_id"] = "autonomy-0123456789ab"
        _recompute_receipt_digest(receipt)
    elif case == "installed_sha_recomputed":
        receipt["projection"]["installed_sha"] = "d" * 40
        _recompute_receipt_digest(receipt)
    elif case == "release_sha_recomputed":
        receipt["projection"]["release_sha"] = "d" * 40
        _recompute_receipt_digest(receipt)
    elif case == "observed_at_invalid":
        receipt["observed_at"] = "2026-02-30T12:00:00Z"
    elif case == "observed_at_noncanonical":
        receipt["observed_at"] = "2026-08-24t12:00:00z"
    elif case == "observed_at_missing":
        del receipt["observed_at"]
    elif case == "observed_at_nonstring":
        receipt["observed_at"] = 1789548398
    elif case == "tool_version_wrong":
        receipt["tool_version"] = None
    elif case == "tool_version_missing":
        del receipt["tool_version"]
    elif case == "extra_top_level_field":
        receipt["extra"] = "forbidden"
    elif case == "renamed_top_level_field":
        del receipt["tool_version"]
        receipt["tool_versions"] = control.TOOL_VERSION
    elif case == "wrong_schema_version":
        receipt["schema_version"] = "mastermind.executive_ceo_submit_receipt/v2"
    elif case == "wrong_state":
        receipt["state"] = "CEO_SUBMIT_DISARMED"
    elif case == "wrong_operation":
        receipt["operation"] = "CEO_SUBMIT_DISARM"
    elif case == "state_operation_mismatch":
        receipt["state"] = "CEO_SUBMIT_DISARMED"
        receipt["projection"]["ceo_submit_armed"] = False
        _recompute_receipt_digest(receipt)
    elif case == "projection_nonobject":
        receipt["projection"] = []
    elif case == "receipt_nonobject":
        receipt = [receipt]
    elif case == "projection_field_missing":
        del receipt["projection"]["installed_sha"]
    elif case == "projection_field_extra":
        receipt["projection"]["extra"] = "forbidden"
    elif case == "projection_digest_wrong":
        receipt["projection_digest"] = "0" * 64
    elif case == "projection_digest_wrong_type":
        receipt["projection_digest"] = 64
    elif case == "projection_digest_missing":
        del receipt["projection_digest"]

    assert (
        control.validate_ceo_submit_receipt_document(receipt, armed=True)
        is (case in {"installed_sha_recomputed", "release_sha_recomputed"})
    )
    assert (
        _direct_ceo_submit_sink_eligible(
            host, binding, worker, worker_sha, receipt
        )
        is False
    )
    host.receipt = receipt
    host.reset_ledgers()
    status = control.evaluate_ceo_submit_status(host, _ceo_submit_request())
    assert status.state == "CEO_SUBMIT_ARMED_UNBOUND"
    assert host.control_writes == host.worker_writes == host.receipt_writes == 0
    assert host.marker is False
    assert host.phases == []

    control.main(["ceo-submit-status", "--expected-sha", SHA], host=host, now=lambda: NOW)
    document = json.loads(capsys.readouterr().out)
    assert document["code"] == "ceo_submit_armed_unbound"
    assert document["state"] == "CEO_SUBMIT_ARMED_UNBOUND"
    assert host.control_writes == host.worker_writes == host.receipt_writes == 0
    assert host.marker is False
    assert host.phases == []
    assert expected_transaction == "autonomy-feedfacec0de"


@pytest.mark.parametrize(
    "value", [[{"schema_version": "x"}], "not-an-object", 17, None]
)
def test_nonobject_receipt_is_refused_at_every_level(value, capsys):
    host, binding, worker, worker_sha = _sealed_ceo_submit_evidence()
    assert control.validate_ceo_submit_receipt_document(value, armed=True) is False
    assert (
        _direct_ceo_submit_sink_eligible(host, binding, worker, worker_sha, value)
        is False
    )
    host.receipt = value
    host.reset_ledgers()
    assert (
        control.evaluate_ceo_submit_status(host, _ceo_submit_request()).state
        == "CEO_SUBMIT_ARMED_UNBOUND"
    )
    control.main(["ceo-submit-status", "--expected-sha", SHA], host=host, now=lambda: NOW)
    document = json.loads(capsys.readouterr().out)
    assert document["code"] == "ceo_submit_armed_unbound"
    assert host.control_writes == host.worker_writes == host.receipt_writes == 0
    assert host.marker is False
    assert host.phases == []


def _strict_receipt_payload(raw):
    host = control.ProductionCeoSubmitHost()
    read = control._read_root_file

    def bounded_read(*args, **kwargs):
        if len(raw) > control._MAX_JSON_BYTES:
            raise control.HostControlError("config_identity_unavailable")
        return read(*args, **kwargs)

    with mock.patch.object(control.Path, "exists", return_value=True), mock.patch.object(
        control.Path, "is_symlink", return_value=False
    ), mock.patch.object(
        control, "_read_root_file", side_effect=bounded_read
    ):
        return host.existing_ceo_submit_receipt()


class _RawReceiptCeoSubmitHost(FakeCeoSubmitHost):
    def __init__(self, raw):
        super().__init__()
        self.control_config["ceo_submit_armed"] = True
        self.raw_receipt = raw

    def existing_ceo_submit_receipt(self):
        return _strict_receipt_payload(self.raw_receipt)


@pytest.mark.parametrize(
    "case,raw",
    [
        ("duplicate_top_level_key", b'{"schema_version":"a","schema_version":"b"}'),
        ("non_utf8", b"\xff\xfe"),
        ("non_json", b"not-json"),
        ("oversize", b"x" * (control._MAX_JSON_BYTES + 1)),
    ],
)
def test_production_receipt_read_boundary_refuses_invalid_bytes(case, raw):
    assert _strict_receipt_payload(raw) is None


def test_production_receipt_read_boundary_refuses_duplicate_valid_keys():
    host = _armed_ceo_submit_host()
    raw = control._encoded_json(host.receipt)
    last_transaction = raw.rfind(b'"transaction_id": "autonomy-feedfacec0de"')
    assert last_transaction != -1
    suffix_start = last_transaction + len(
        b'"transaction_id": "autonomy-feedfacec0de"'
    )
    duplicated = (
        raw[:suffix_start]
        + b', "transaction_id": "autonomy-feedfacec0de"'
        + raw[suffix_start:]
    )
    assert duplicated != raw
    assert _strict_receipt_payload(duplicated) is None
    json.loads(duplicated, object_pairs_hook=dict)


@pytest.mark.parametrize(
    "case,raw",
    [
        ("duplicate_top_level_key", b'{"schema_version":"a","schema_version":"b"}'),
        ("non_utf8", b"\xff\xfe"),
        ("non_json", b"not-json"),
        ("oversize", b"x" * (control._MAX_JSON_BYTES + 1)),
    ],
)
def test_invalid_raw_receipt_bytes_read_back_unbound_through_the_real_cli(case, raw, capsys):
    host = _RawReceiptCeoSubmitHost(raw)
    assert (
        control.evaluate_ceo_submit_status(host, _ceo_submit_request()).state
        == "CEO_SUBMIT_ARMED_UNBOUND"
    )
    assert host.control_writes == host.worker_writes == host.receipt_writes == 0
    assert host.marker is False
    assert host.phases == []
    exit_code = control.main(
        ["ceo-submit-status", "--expected-sha", SHA], host=host, now=lambda: NOW
    )
    document = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert document["code"] == "ceo_submit_armed_unbound"
    assert host.control_writes == host.worker_writes == host.receipt_writes == 0


def test_canonical_real_writer_receipt_remains_eligible_and_armed(capsys):
    host, binding, worker, worker_sha = _sealed_ceo_submit_evidence()
    assert (
        _direct_ceo_submit_sink_eligible(
            host, binding, worker, worker_sha, host.receipt
        )
        is True
    )
    assert (
        control.evaluate_ceo_submit_status(host, _ceo_submit_request()).state
        == "CEO_SUBMIT_ARMED"
    )
    host.reset_ledgers()
    assert (
        control.main(
            ["ceo-submit-status", "--expected-sha", SHA], host=host, now=lambda: NOW
        )
        == 0
    )
    document = json.loads(capsys.readouterr().out)
    assert document["code"] == "ceo_submit_armed"
    assert host.control_writes == host.worker_writes == host.receipt_writes == 0
    assert host.marker is False
    assert host.phases == []


@pytest.mark.parametrize(
    "case", ["worker_arm_true", "worker_byte_drift", "arm_fact_drift"]
)
def test_current_worker_drift_is_refused_at_every_level(case, capsys):
    host, binding, worker, worker_sha = _sealed_ceo_submit_evidence()
    receipt = copy.deepcopy(host.receipt)

    if case == "worker_arm_true":
        worker = {**worker, "operator_harness_armed": True}
    elif case == "worker_byte_drift":
        worker = {**worker, "unrelated": "byte-changing-value"}
        worker_sha = control.sha256_bytes(control.encode_config(worker))
    else:
        worker = {**worker, "operator_harness_armed": True}
        worker_sha = control.sha256_bytes(control.encode_config(worker))
        receipt["projection"]["worker_operator_harness_armed"] = True
        receipt["projection"]["worker_config_sha256"] = worker_sha
        _recompute_receipt_digest(receipt)

    assert (
        _direct_ceo_submit_sink_eligible(host, binding, worker, worker_sha, receipt)
        is False
    )
    host.worker_config = worker
    host.receipt = receipt
    host.reset_ledgers()
    assert (
        control.evaluate_ceo_submit_status(host, _ceo_submit_request()).state
        == "CEO_SUBMIT_ARMED_UNBOUND"
    )
    assert host.control_writes == host.worker_writes == host.receipt_writes == 0
    assert host.marker is False
    assert host.phases == []

    exit_code = control.main(
        ["ceo-submit-status", "--expected-sha", SHA], host=host, now=lambda: NOW
    )
    document = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert document["code"] == "ceo_submit_armed_unbound"
    assert host.control_writes == host.worker_writes == host.receipt_writes == 0
    assert host.marker is False
    assert host.phases == []


def test_unrelated_later_coo_field_change_does_not_invalidate_the_ceo_submit_receipt():
    host = FakeCeoSubmitHost()
    control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)
    receipt = host.receipt
    worker_config = copy.deepcopy(host.worker_config)
    worker_config_sha256 = control.sha256_bytes(control.encode_config(worker_config))
    binding = host.executive_app_binding()

    assert (
        control.ceo_submit_sink_eligible(
            control_config=host.control_config,
            worker_config=worker_config,
            worker_config_sha256=worker_config_sha256,
            receipt=receipt,
            binding=binding,
            expected_sha=SHA,
            installed_sha=SHA,
        )
        is True
    )
    whole_before = control.sha256_bytes(control.encode_config(host.control_config))

    host.control_config["coo_tick_interval_seconds"] = 45.0
    host.control_config["coo_model_alias"] = "coo.next"
    host.control_config["later_unrelated_blob"] = {"added": ["after", "arm"]}
    whole_after = control.sha256_bytes(control.encode_config(host.control_config))

    assert whole_before != whole_after
    assert (
        control.ceo_submit_sink_eligible(
            control_config=host.control_config,
            worker_config=worker_config,
            worker_config_sha256=worker_config_sha256,
            receipt=receipt,
            binding=binding,
            expected_sha=SHA,
            installed_sha=SHA,
        )
        is True
    )

    host.control_config["ceo_submit_armed"] = False
    assert (
        control.ceo_submit_sink_eligible(
            control_config=host.control_config,
            worker_config=worker_config,
            worker_config_sha256=worker_config_sha256,
            receipt=receipt,
            binding=binding,
            expected_sha=SHA,
            installed_sha=SHA,
        )
        is False
    )
    host.control_config["ceo_submit_armed"] = True
    assert (
        control.ceo_submit_sink_eligible(
            control_config={**host.control_config, "ceo_ingress_app_peer_uid": 459},
            worker_config=worker_config,
            worker_config_sha256=worker_config_sha256,
            receipt=receipt,
            binding=binding,
            expected_sha=SHA,
            installed_sha=SHA,
        )
        is False
    )


def test_ceo_submit_arm_performs_no_provider_call_job_submission_or_worker_effect(
    monkeypatch,
):
    def _refuse(*_args, **_kwargs):
        raise AssertionError("CEO-submit ARM must not touch the network or a subprocess")

    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr(subprocess, "run", _refuse)
    monkeypatch.setattr(subprocess, "Popen", _refuse)
    monkeypatch.setattr(os, "system", _refuse)

    host = FakeCeoSubmitHost()
    before_worker = control.encode_config(host.worker_config)

    result = control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)

    assert result == control.TransactionResult(
        state="CEO_SUBMIT_ARMED",
        status="CEO_SUBMIT_ARMED",
        transaction_id="autonomy-feedfacec0de",
        replayed=False,
    )
    assert host.calls == list(FakeCeoSubmitHost.CEO_GATES)
    assert host.phases == list(FakeCeoSubmitHost.CEO_PHASES)
    assert host.worker_replace_calls == 0
    assert control.encode_config(host.worker_config) == before_worker
    assert host.worker_config["operator_harness_armed"] is False
    assert host.control_config["coo_autonomy_armed"] is False
    assert host.control_config["coo_operator_harness_armed"] is False


def test_ceo_submit_rollback_and_ambiguity_are_typed_and_sticky_to_the_operation(
    monkeypatch,
):
    host = FakeCeoSubmitHost(fail_after="candidates")
    with pytest.raises(control.ArmTransactionError) as raised:
        control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)
    assert raised.value.code == "arm_rolled_back"
    assert host.phases == ["lock", "candidates"]
    assert host.control_config["ceo_submit_armed"] is False
    assert host.marker is False
    assert host.rollback_receipt["state"] == "CEO_SUBMIT_DISARMED"
    assert host.rollback_receipt["operation"] == "CEO_SUBMIT_DISARM"
    assert host.rollback_receipt["transaction_id"] == "autonomy-feedfacec0de"
    assert host.rollback_receipt["projection"]["ceo_submit_armed"] is False

    sticky = FakeCeoSubmitHost(fail_after="control", rollback_fails=True)
    with pytest.raises(control.TransactionEffectUnknown) as unknown:
        control.execute_ceo_submit_arm(sticky, _ceo_submit_request(), now=NOW)
    assert unknown.value.code == "effect_unknown"
    assert sticky.marker is True
    assert sticky.rollback_receipt is None
    assert control.CEO_SUBMIT_OPERATIONS == frozenset(
        {"CEO_SUBMIT_ARM", "CEO_SUBMIT_DISARM"}
    )

    # A typed refusal raised AFTER the control replace is still an operation
    # failure: it must roll back the postimage rather than surface as a clean
    # refusal that would hide an armed control.json.
    real_build = control.build_ceo_submit_receipt

    def _drift(transaction, admission, *, armed, now):
        if armed:
            raise control.CeoSubmitAdmissionError("ceo_submit_config_schema_drift")
        return real_build(transaction, admission, armed=armed, now=now)

    post_write = FakeCeoSubmitHost()
    monkeypatch.setattr(control, "build_ceo_submit_receipt", _drift)
    with pytest.raises(control.ArmTransactionError) as rolled:
        control.execute_ceo_submit_arm(post_write, _ceo_submit_request(), now=NOW)
    assert rolled.value.code == "arm_rolled_back"
    assert "control" in post_write.phases
    assert post_write.control_config["ceo_submit_armed"] is False
    assert post_write.marker is False


def _armed_ceo_submit_host(**overrides):
    """A fake host that has already run a real CEO-submit ARM transaction."""

    host = FakeCeoSubmitHost(**overrides)
    control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)
    assert host.control_config["ceo_submit_armed"] is True
    return host


def test_ceo_submit_disarm_uses_the_same_global_owner_and_changes_only_the_ceo_flag():
    host = _armed_ceo_submit_host()
    before = copy.deepcopy(host.control_config)
    before_worker = control.encode_config(host.worker_config)
    before_worker_sha = control.sha256_bytes(before_worker)
    host.reset_ledgers()

    result = control.execute_ceo_submit_disarm(host, _ceo_submit_request(), now=NOW)

    assert result == control.TransactionResult(
        state="CEO_SUBMIT_DISARMED",
        status="CEO_SUBMIT_DISARMED",
        transaction_id="autonomy-feedfacec0de",
        replayed=False,
    )
    assert host.operations == ["CEO_SUBMIT_DISARM"]
    assert host.phases == list(FakeCeoSubmitHost.CEO_PHASES)
    assert host.phases[0] == "lock"
    assert host.calls == [
        "root",
        "install",
        "configs",
        "separation",
        "binding",
        "transaction",
    ]
    assert host.marker is False
    assert set(host.control_config) == set(before)
    assert host.control_config == {**before, "ceo_submit_armed": False}
    changed = {key for key in before if before[key] != host.control_config[key]}
    assert changed == {"ceo_submit_armed"}
    assert host.control_writes == 1
    assert host.worker_writes == 0
    assert host.worker_replace_calls == 0
    after_worker = control.encode_config(host.worker_config)
    assert after_worker == before_worker
    assert control.sha256_bytes(after_worker) == before_worker_sha
    assert host.last_transaction.candidates.worker_bytes == before_worker
    assert host.last_transaction.candidates.worker_sha256 == before_worker_sha
    assert host.last_transaction.candidates.control_bytes == control.encode_config(
        {**before, "ceo_submit_armed": False}
    )
    assert host.receipt["state"] == "CEO_SUBMIT_DISARMED"
    assert host.receipt["operation"] == "CEO_SUBMIT_DISARM"
    assert host.receipt["projection"]["ceo_submit_armed"] is False

    # The disarm rides the ONE global owner: no second lock exists anywhere.
    source = Path(control.__file__).read_text(encoding="utf-8")
    assert "ceo-submit-transaction.lock" not in source
    lock_paths = {
        name
        for name, value in vars(control).items()
        if isinstance(value, Path) and "lock" in value.name.lower()
    }
    assert lock_paths == {"AUTONOMY_TRANSACTION"}
    disarm = source.split("def execute_ceo_submit_disarm(", 1)[1].split("\ndef ", 1)[0]
    assert "begin_ceo_submit_transaction" in disarm
    assert 'operation="CEO_SUBMIT_DISARM"' in disarm
    assert "host.replace_control_config" in disarm
    assert "replace_worker_config" not in disarm
    assert "replace_autonomy_receipt" not in disarm


def test_ceo_submit_disarm_preserves_app_install_acl_and_every_unrelated_value():
    host = _armed_ceo_submit_host()
    # Later full autonomy is armed ON TOP of the armed CEO-submit sink; the fake
    # host is told coexistence is proven, so the disarm is admitted.
    host.control_config.update(
        {
            "ceo_ingress_app_peer_uid": 458,
            "ceo_ingress_app_armed": False,
            "ceo_ingress_peer_uid": 452,
            "ceo_ingress_socket_path": "/var/run/mastermind-executive/ceo-ingress.sock",
            "ceo_ingress_launchd_socket_name": "CeoIngress",
            "ceo_ingress_app_macro_root": CEO_SUBMIT_APP_MACRO_ROOT,
            "coo_autonomy_armed": True,
            "coo_operator_harness_armed": False,
            "coo_tick_interval_seconds": 42.5,
            "coo_model_alias": "coo.sealed.vNEXT",
            "terminal_return_armed": False,
            "preserved": {"alpha": 1, "nested": {"beta": ["x", {"gamma": 3}]}},
        }
    )
    host.worker_config["preserved"] = ["beta", {"gamma": [1, 2]}]
    host.safe_coexistence = True
    host.reset_ledgers()
    before = copy.deepcopy(host.control_config)
    before_worker_bytes = control.encode_config(host.worker_config)
    before_worker_sha = control.sha256_bytes(before_worker_bytes)
    before_candidate_bytes = control.encode_config(before)

    result = control.execute_ceo_submit_disarm(host, _ceo_submit_request(), now=NOW)

    assert result.state == "CEO_SUBMIT_DISARMED"
    assert set(host.control_config) == set(before)
    assert host.control_config == {**before, "ceo_submit_armed": False}
    changed = {key for key in before if before[key] != host.control_config[key]}
    assert changed == {"ceo_submit_armed"}
    # Byte identity of the whole document with exactly one flag flipped.
    expected_bytes = control.encode_config({**before, "ceo_submit_armed": False})
    assert control.encode_config(host.control_config) == expected_bytes
    assert expected_bytes != before_candidate_bytes
    assert control.encode_config(host.control_config) == control.encode_config(
        {**before, "ceo_submit_armed": False}
    )
    # The UID458 App install / ACL keys and the socket topology survive verbatim.
    assert host.control_config["ceo_ingress_app_peer_uid"] == 458
    assert host.control_config["ceo_ingress_app_armed"] is False
    assert host.control_config["ceo_ingress_peer_uid"] == 452
    assert (
        host.control_config["ceo_ingress_socket_path"]
        == "/var/run/mastermind-executive/ceo-ingress.sock"
    )
    assert host.control_config["ceo_ingress_launchd_socket_name"] == "CeoIngress"
    assert host.control_config["ceo_ingress_app_macro_root"] == CEO_SUBMIT_APP_MACRO_ROOT
    # COO authority is NOT the CEO-submit operation's to clear, even when armed.
    assert host.control_config["coo_autonomy_armed"] is True
    assert host.control_config["coo_operator_harness_armed"] is False
    assert host.control_config["coo_tick_interval_seconds"] == 42.5
    assert host.control_config["coo_model_alias"] == "coo.sealed.vNEXT"
    assert host.control_config["terminal_return_armed"] is False
    assert host.control_config["preserved"] == {
        "alpha": 1,
        "nested": {"beta": ["x", {"gamma": 3}]},
    }
    # The worker config is never a CEO-submit write target, byte for byte.
    after_worker_bytes = control.encode_config(host.worker_config)
    assert after_worker_bytes == before_worker_bytes
    assert control.sha256_bytes(after_worker_bytes) == before_worker_sha
    assert host.worker_writes == 0
    assert host.worker_replace_calls == 0
    assert host.last_transaction.candidates.worker_bytes == before_worker_bytes
    assert host.last_transaction.candidates.worker_sha256 == before_worker_sha


def test_repeated_ceo_submit_disarm_is_a_read_only_replay_that_never_rewrites_the_receipt():
    host = _armed_ceo_submit_host()
    first = control.execute_ceo_submit_disarm(host, _ceo_submit_request(), now=NOW)
    assert first.replayed is False
    assert first.transaction_id == "autonomy-feedfacec0de"
    sealed = host.receipt
    sealed_bytes = control._encoded_json(sealed)
    sealed_control_bytes = control.encode_config(host.control_config)
    host.reset_ledgers()

    second = control.execute_ceo_submit_disarm(host, _ceo_submit_request(), now=NOW)

    assert second == control.TransactionResult(
        state="CEO_SUBMIT_DISARMED",
        status="CEO_SUBMIT_DISARMED",
        transaction_id=sealed["transaction_id"],
        replayed=True,
    )
    # No phase was entered at all: no lock, no write, no service boundary.
    assert host.phases == []
    assert host.operations == []
    # The extra gate is the R18-B4 read-only free-owner proof.
    assert host.calls == ["root", "install", "configs", "transaction"]
    assert host.control_writes == 0
    assert host.worker_writes == 0
    assert host.receipt_writes == 0
    assert host.reconcile_calls == 0
    assert host.admission_bound_calls == 0
    assert host.marker is False
    assert control.encode_config(host.control_config) == sealed_control_bytes
    # The receipt is the SAME object and the SAME value: nothing was rewritten.
    assert host.receipt is sealed
    assert host.receipt == sealed
    assert control._encoded_json(host.receipt) == sealed_bytes


def test_ceo_submit_disarm_refuses_when_later_full_autonomy_is_armed_without_proven_coexistence():
    # DEFAULT IS REFUSAL: the flag is False on the fake host and False in source.
    assert FakeCeoSubmitHost().safe_coexistence is False
    source = Path(control.__file__).read_text(encoding="utf-8")
    production = source.split("class ProductionCeoSubmitHost", 1)[1]
    body = production.split("def proves_safe_coexistence", 1)[1].split("\n    def ", 1)[0]
    assert body.strip().endswith("return False")

    host = _armed_ceo_submit_host()
    host.control_config["coo_autonomy_armed"] = True
    before = copy.deepcopy(host.control_config)
    sealed = host.receipt
    host.reset_ledgers()

    with pytest.raises(control.CeoSubmitAdmissionError) as raised:
        control.execute_ceo_submit_disarm(host, _ceo_submit_request(), now=NOW)

    assert raised.value.code == "full_autonomy_armed_unsafe_coexistence"
    assert host.calls == ["root", "install", "configs", "separation"]
    assert host.phases == []
    assert host.marker is False
    assert host.control_writes == 0
    assert host.receipt_writes == 0
    assert host.receipt is sealed
    assert host.reconcile_calls == 0
    assert host.admission_bound_calls == 0
    assert host.control_config == before
    assert host.control_config["ceo_submit_armed"] is True

    # Same state, but the source now proves safe coexistence: it proceeds.
    host.safe_coexistence = True
    host.reset_ledgers()
    result = control.execute_ceo_submit_disarm(host, _ceo_submit_request(), now=NOW)
    assert result.state == "CEO_SUBMIT_DISARMED"
    assert result.replayed is False
    assert host.control_config["ceo_submit_armed"] is False
    assert host.control_config["coo_autonomy_armed"] is True
    assert host.reconcile_calls == 1 and host.admission_bound_calls == 1


def test_an_incomplete_transaction_of_another_operation_is_a_typed_hold_not_effect_unknown():
    assert control.ceo_submit_effect_unknown_sticky("CEO_SUBMIT_ARM", "CEO_SUBMIT_ARM") is True
    assert (
        control.ceo_submit_effect_unknown_sticky("CEO_SUBMIT_DISARM", "CEO_SUBMIT_DISARM")
        is True
    )
    assert control.ceo_submit_effect_unknown_sticky(None, "CEO_SUBMIT_ARM") is False
    assert control.ceo_submit_effect_unknown_sticky("ARM", "CEO_SUBMIT_ARM") is False
    assert control.ceo_submit_effect_unknown_sticky("DISARM", "CEO_SUBMIT_ARM") is False
    assert (
        control.ceo_submit_effect_unknown_sticky("CEO_SUBMIT_DISARM", "CEO_SUBMIT_ARM") is False
    )

    # A COO marker, an unknown marker and the OTHER CEO-submit verb are all the
    # typed HOLD, never EFFECT_UNKNOWN.
    for marker in ("ARM", "DISARM", "CEO_SUBMIT_ARM"):
        host = _armed_ceo_submit_host()
        host.incomplete_marker_operation = marker
        sealed = host.receipt
        host.reset_ledgers()
        before = copy.deepcopy(host.control_config)

        with pytest.raises(control.CeoSubmitAdmissionError) as raised:
            control.execute_ceo_submit_disarm(host, _ceo_submit_request(), now=NOW)

        assert raised.value.code == "ceo_submit_transaction_incomplete"
        assert not isinstance(raised.value, control.TransactionEffectUnknown)
        assert host.phases == []
        assert host.control_writes == 0
        assert host.receipt_writes == 0
        assert host.receipt is sealed
        assert host.control_config == before
        # The seeded extant marker is untouched: nothing was begun, nothing cleared.
        assert host.incomplete_marker_operation == marker
        assert host.operations == []

    arm_host = FakeCeoSubmitHost()
    arm_host.incomplete_marker_operation = "CEO_SUBMIT_DISARM"
    with pytest.raises(control.CeoSubmitAdmissionError) as arm_raised:
        control.execute_ceo_submit_arm(arm_host, _ceo_submit_request(), now=NOW)
    assert arm_raised.value.code == "ceo_submit_transaction_incomplete"
    assert not isinstance(arm_raised.value, control.TransactionEffectUnknown)
    assert arm_host.phases == []
    assert arm_host.control_writes == 0


def test_post_write_ambiguity_is_effect_unknown_and_sticky_to_the_same_operation():
    host = FakeCeoSubmitHost()
    host.incomplete_marker_operation = "CEO_SUBMIT_ARM"

    with pytest.raises(control.TransactionEffectUnknown) as first:
        control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)

    assert first.value.code == "effect_unknown"
    assert host.incomplete_marker_operation == "CEO_SUBMIT_ARM"
    assert host.calls == []
    assert host.phases == []
    assert host.control_writes == 0
    assert host.receipt_writes == 0
    assert host.receipt is None

    with pytest.raises(control.TransactionEffectUnknown) as again:
        control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)

    assert again.value.code == "effect_unknown"
    assert host.calls == []
    assert host.phases == []
    assert host.control_writes == 0
    assert host.receipt_writes == 0
    assert host.receipt is None
    assert host.incomplete_marker_operation == "CEO_SUBMIT_ARM"
    assert host.operations == []

    # The same stickiness holds in the disarm direction: never re-attempt the write.
    armed = _armed_ceo_submit_host()
    armed.incomplete_marker_operation = "CEO_SUBMIT_DISARM"
    sealed = armed.receipt
    armed.reset_ledgers()
    before = copy.deepcopy(armed.control_config)

    with pytest.raises(control.TransactionEffectUnknown) as disarm_first:
        control.execute_ceo_submit_disarm(armed, _ceo_submit_request(), now=NOW)
    assert disarm_first.value.code == "effect_unknown"
    assert armed.control_config == before
    assert armed.control_writes == 0
    assert armed.phases == []
    assert armed.receipt is sealed

    with pytest.raises(control.TransactionEffectUnknown):
        control.execute_ceo_submit_disarm(armed, _ceo_submit_request(), now=NOW)
    assert armed.control_config == before
    assert armed.control_writes == 0
    assert armed.receipt_writes == 0
    assert armed.phases == []



def test_ceo_submit_disarm_never_replays_across_an_in_flight_ceo_submit_arm():
    # R18-B4: a CEO_SUBMIT_ARM still in flight before its control replace leaves
    # an extant marker naming a DIFFERENT operation.  That is an occupied global
    # owner, never a free one, so the disarmed REPLAY must be refused.
    def _assert_zero_writes(host, before):
        assert host.control_writes == 0
        assert host.worker_writes == 0
        assert host.receipt_writes == 0
        assert host.reconcile_calls == 0
        assert host.admission_bound_calls == 0
        assert host.phases == []
        assert host.operations == []
        assert host.marker is False
        assert host.receipt is None
        assert control.encode_config(host.control_config) == control.encode_config(
            before
        )

    host = FakeCeoSubmitHost()
    host.incomplete_marker_operation = "CEO_SUBMIT_ARM"
    before = copy.deepcopy(host.control_config)

    with pytest.raises(control.CeoSubmitAdmissionError) as refused:
        control.execute_ceo_submit_disarm(host, _ceo_submit_request(), now=NOW)

    assert refused.value.code == "ceo_submit_transaction_incomplete"
    assert not isinstance(refused.value, control.TransactionEffectUnknown)
    _assert_zero_writes(host, before)
    # The seeded marker is untouched: the refusal read it, it did not consume it.
    assert host.incomplete_marker_operation == "CEO_SUBMIT_ARM"

    direct = FakeCeoSubmitHost()
    direct.incomplete_marker_operation = "CEO_SUBMIT_ARM"
    direct_before = copy.deepcopy(direct.control_config)

    with pytest.raises(control.CeoSubmitAdmissionError) as admission_refused:
        control.evaluate_ceo_submit_disarm_admission(
            direct, _ceo_submit_request(), now=NOW
        )

    assert admission_refused.value.code == "ceo_submit_transaction_incomplete"
    assert not isinstance(admission_refused.value, control.TransactionEffectUnknown)
    _assert_zero_writes(direct, direct_before)
    assert direct.incomplete_marker_operation == "CEO_SUBMIT_ARM"


def test_ceo_submit_disarm_never_replays_across_a_coo_or_unclassifiable_global_owner():
    # R18-B4: the already-disarmed REPLAY may only be taken across a FREE global
    # owner.  A COO ARM/DISARM or an occupied-but-unclassifiable marker is the
    # existing typed HOLD with zero writes, never a success response.
    owners = (
        ("ARM", "ARM"),
        ("DISARM", "DISARM"),
        ("unclassifiable", None),
    )
    for name, operation in owners:
        host = FakeCeoSubmitHost()
        if operation is None:
            host.marker = True
        else:
            host.incomplete_marker_operation = operation
        before = copy.deepcopy(host.control_config)

        with pytest.raises(control.CeoSubmitAdmissionError) as refused:
            control.execute_ceo_submit_disarm(host, _ceo_submit_request(), now=NOW)

        assert refused.value.code == "ceo_submit_transaction_incomplete", name
        assert not isinstance(refused.value, control.TransactionEffectUnknown), name
        assert host.control_writes == 0, name
        assert host.worker_writes == 0, name
        assert host.receipt_writes == 0, name
        assert host.reconcile_calls == 0, name
        assert host.admission_bound_calls == 0, name
        assert host.phases == [], name
        assert host.operations == [], name
        assert host.receipt is None, name
        assert control.encode_config(host.control_config) == control.encode_config(
            before
        ), name
        assert host.incomplete_marker_operation == operation, name
        assert host.marker is (operation is None), name


def test_ceo_submit_status_never_reads_a_verified_state_through_an_occupied_global_owner(
    capsys,
):
    # R18-B4: a verified CEO snapshot is never read THROUGH an occupied global
    # owner.  Same-CEO-operation ambiguity keeps its EFFECT_UNKNOWN; any
    # DIFFERENT occupied owner -- a COO ARM/DISARM or an unclassifiable marker --
    # returns the existing typed unverified/HOLD through that same owner.
    def observe(host):
        """Return either the readback result or the refusal it raised."""

        try:
            return control.evaluate_ceo_submit_status(host, _ceo_submit_request())
        except BaseException as exc:  # noqa: BLE001 - the refusal IS the evidence
            return exc

    def make_disarmed():
        return FakeCeoSubmitHost()

    def make_armed():
        host = _armed_ceo_submit_host()
        host.reset_ledgers()
        return host

    for label, make in (("disarmed", make_disarmed), ("armed", make_armed)):
        for occupied in ("CEO_SUBMIT_ARM", "CEO_SUBMIT_DISARM"):
            host = make()
            host.incomplete_marker_operation = occupied
            before = copy.deepcopy(host.control_config)

            observed = observe(host)

            assert isinstance(observed, control.TransactionEffectUnknown), (
                label,
                occupied,
            )
            assert observed.code == "effect_unknown", (label, occupied)
            assert not isinstance(observed, control.TransactionResult), (
                label,
                occupied,
            )
            assert getattr(observed, "state", None) is None, (label, occupied)
            assert host.control_writes == 0, (label, occupied)
            assert host.receipt_writes == 0, (label, occupied)
            assert host.phases == [], (label, occupied)
            assert control.encode_config(host.control_config) == control.encode_config(
                before
            ), (label, occupied)

        for occupied in ("ARM", "DISARM", None):
            host = make()
            if occupied is None:
                host.marker = True
            else:
                host.incomplete_marker_operation = occupied
            before = copy.deepcopy(host.control_config)

            observed = observe(host)

            assert isinstance(observed, control.CeoSubmitAdmissionError), (
                label,
                occupied,
            )
            assert observed.code == "ceo_submit_transaction_incomplete", (
                label,
                occupied,
            )
            assert not isinstance(observed, control.TransactionEffectUnknown), (
                label,
                occupied,
            )
            assert not isinstance(observed, control.TransactionResult), (
                label,
                occupied,
            )
            assert getattr(observed, "state", None) is None, (label, occupied)
            assert host.control_writes == 0, (label, occupied)
            assert host.receipt_writes == 0, (label, occupied)
            assert host.phases == [], (label, occupied)
            assert control.encode_config(host.control_config) == control.encode_config(
                before
            ), (label, occupied)

    # The CLI surface answers the same typed HOLD, never a state claim.
    cli_host = FakeCeoSubmitHost()
    cli_host.incomplete_marker_operation = "ARM"

    exit_code = control.main(
        ["ceo-submit-status", "--expected-sha", SHA], host=cli_host, now=lambda: NOW
    )

    assert exit_code == 2
    document = json.loads(capsys.readouterr().out)
    assert document["code"] == "ceo_submit_transaction_incomplete"
    assert document["state"] == "UNKNOWN"
    assert document["status"] == "CEO_SUBMIT_UNVERIFIED"
    assert document["transaction_id"] is None
    assert document["replayed"] is False
    assert cli_host.control_writes == 0
    assert cli_host.receipt_writes == 0
    assert cli_host.phases == []
    assert cli_host.marker is False


def test_ceo_submit_disarm_replay_across_a_free_owner_stays_read_only_and_byte_identical():
    # R18-B4: across a genuinely FREE owner the replay still keeps every R9
    # guarantee -- same object, same bytes, no lock, no write -- while proving
    # the owner free through the ONE existing AUTONOMY_TRANSACTION stat probe.
    host = _armed_ceo_submit_host()
    first = control.execute_ceo_submit_disarm(host, _ceo_submit_request(), now=NOW)
    assert first.replayed is False
    sealed = host.receipt
    sealed_bytes = control._encoded_json(sealed)
    sealed_control_bytes = control.encode_config(host.control_config)
    host.reset_ledgers()

    replay = control.execute_ceo_submit_disarm(host, _ceo_submit_request(), now=NOW)

    assert replay.replayed is True
    assert replay.state == "CEO_SUBMIT_DISARMED"
    assert replay.status == "CEO_SUBMIT_DISARMED"
    assert replay.transaction_id == sealed["transaction_id"]
    assert host.control_writes == 0
    assert host.worker_writes == 0
    assert host.receipt_writes == 0
    assert host.reconcile_calls == 0
    assert host.admission_bound_calls == 0
    assert host.phases == []
    assert host.operations == []
    assert host.marker is False
    assert control.encode_config(host.control_config) == sealed_control_bytes
    assert host.receipt is sealed
    assert host.receipt == sealed
    assert control._encoded_json(host.receipt) == sealed_bytes
    # The free-owner proof actually ran: the read-only stat probe is the last call.
    assert host.calls == ["root", "install", "configs", "transaction"]


def test_ceo_submit_disarm_same_operation_marker_stays_sticky_effect_unknown_on_a_disarmed_host():
    # R18-B4: the SAME-verb marker keeps R9 stickiness -- EFFECT_UNKNOWN, never a
    # typed HOLD and never a replay admission -- even on a disarmed host.
    direct = FakeCeoSubmitHost()
    direct.incomplete_marker_operation = "CEO_SUBMIT_DISARM"
    direct_before = copy.deepcopy(direct.control_config)

    with pytest.raises(control.TransactionEffectUnknown) as admission_unknown:
        control.evaluate_ceo_submit_disarm_admission(
            direct, _ceo_submit_request(), now=NOW
        )

    assert admission_unknown.value.code == "effect_unknown"
    assert not isinstance(admission_unknown.value, control.CeoSubmitAdmissionError)
    assert direct.control_writes == 0
    assert direct.receipt_writes == 0
    assert direct.phases == []
    assert direct.operations == []
    assert direct.receipt is None
    assert direct.incomplete_marker_operation == "CEO_SUBMIT_DISARM"
    assert control.encode_config(direct.control_config) == control.encode_config(
        direct_before
    )

    host = FakeCeoSubmitHost()
    host.incomplete_marker_operation = "CEO_SUBMIT_DISARM"
    before = copy.deepcopy(host.control_config)

    for _ in range(2):
        with pytest.raises(control.TransactionEffectUnknown) as refused:
            control.execute_ceo_submit_disarm(host, _ceo_submit_request(), now=NOW)
        assert refused.value.code == "effect_unknown"
        assert not isinstance(refused.value, control.CeoSubmitAdmissionError)
        assert host.control_writes == 0
        assert host.worker_writes == 0
        assert host.receipt_writes == 0
        assert host.reconcile_calls == 0
        assert host.admission_bound_calls == 0
        assert host.phases == []
        assert host.operations == []
        assert host.receipt is None
        assert host.marker is False
        assert control.encode_config(host.control_config) == control.encode_config(
            before
        )
        assert host.incomplete_marker_operation == "CEO_SUBMIT_DISARM"

def test_the_control_service_boundary_is_bounded_to_one_reconcile_and_one_admission_bound():
    arm_host = FakeCeoSubmitHost()
    control.execute_ceo_submit_arm(arm_host, _ceo_submit_request(), now=NOW)
    assert arm_host.reconcile_calls == 1
    assert arm_host.admission_bound_calls == 1
    assert arm_host.phases.count("reconciled") == 1
    assert arm_host.phases.count("admission_bound") == 1

    disarm_host = _armed_ceo_submit_host()
    disarm_host.reset_ledgers()
    control.execute_ceo_submit_disarm(disarm_host, _ceo_submit_request(), now=NOW)
    assert disarm_host.reconcile_calls == 1
    assert disarm_host.admission_bound_calls == 1
    assert disarm_host.phases.count("reconciled") == 1
    assert disarm_host.phases.count("admission_bound") == 1

    # Structurally: exactly one reconcile call and one admission-bound probe, no loop.
    source = Path(control.__file__).read_text(encoding="utf-8")
    for function in ("def execute_ceo_submit_arm(", "def execute_ceo_submit_disarm("):
        body = source.split(function, 1)[1].split("\ndef ", 1)[0]
        lines = [line.strip() for line in body.splitlines()]
        assert [
            line for line in lines if "reconcile_control_service" in line
        ] == ["host.reconcile_control_service(request.expected_sha)"]
        # R80: ARM/DISARM ride the renamed CEO-admission proof; the candidate
        # config digest is the freshly-derived postimage's control_sha256.
        bound_lines = [
            line
            for line in lines
            if "prove_control_admission_bound" in line
            and "host.prove_control_admission_bound(request.expected_sha," in line
        ]
        assert len(bound_lines) == 1
        assert "candidate_config_digest=transaction.candidates.control_sha256" in bound_lines[0]
        assert not any(line.startswith(("while ", "for ")) for line in lines)

    def disarm_root(host):
        host.uid = 501

    def disarm_install(host):
        host.installed_sha = "d" * 40

    def disarm_configs(host):
        host.control_config["ceo_submit_armed"] = "yes"

    def disarm_separation(host):
        host.control_config["coo_autonomy_armed"] = True

    def disarm_marker(host):
        host.incomplete_marker_operation = "ARM"

    refusals = (
        ("root", disarm_root, control.HostControlError, "privilege_required"),
        (
            "install",
            disarm_install,
            control.CeoSubmitAdmissionError,
            "release_identity_mismatch",
        ),
        (
            "configs",
            disarm_configs,
            control.CeoSubmitAdmissionError,
            "ceo_submit_config_schema_drift",
        ),
        (
            "separation",
            disarm_separation,
            control.CeoSubmitAdmissionError,
            "full_autonomy_armed_unsafe_coexistence",
        ),
        (
            "marker",
            disarm_marker,
            control.CeoSubmitAdmissionError,
            "ceo_submit_transaction_incomplete",
        ),
    )
    for _label, setup, error, code in refusals:
        host = _armed_ceo_submit_host()
        setup(host)
        host.reset_ledgers()
        with pytest.raises(error) as raised:
            control.execute_ceo_submit_disarm(host, _ceo_submit_request(), now=NOW)
        assert raised.value.code == code
        assert host.reconcile_calls == 0
        assert host.admission_bound_calls == 0
        assert host.phases == []

    arm_refusals = (
        ("root", disarm_root, control.HostControlError, "privilege_required"),
        (
            "install",
            disarm_install,
            control.CeoSubmitAdmissionError,
            "release_identity_mismatch",
        ),
        (
            "configs",
            lambda host: host.control_config.__setitem__("ceo_submit_armed", True),
            control.CeoSubmitAdmissionError,
            "ceo_submit_already_armed",
        ),
    )
    for _label, setup, error, code in arm_refusals:
        host = FakeCeoSubmitHost()
        setup(host)
        host.reset_ledgers()
        with pytest.raises(error) as raised:
            control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)
        assert raised.value.code == code
        assert host.reconcile_calls == 0
        assert host.admission_bound_calls == 0
        assert host.phases == []


def test_manual_config_edit_alone_does_not_make_the_ceo_submit_sink_eligible():
    host = FakeCeoSubmitHost()
    binding = host.executive_app_binding()
    hand_edited = {"ceo_submit_armed": True}

    assert (
        control.ceo_submit_sink_eligible(
            control_config=hand_edited, worker_config=host.worker_config, worker_config_sha256=control.sha256_bytes(control.encode_config(host.worker_config)), receipt=None, binding=binding, expected_sha=SHA, installed_sha=SHA
        )
        is False
    )
    assert (
        control.ceo_submit_sink_eligible(
            control_config={**hand_edited, "coo_tick_interval_seconds": 15.0},
            worker_config=host.worker_config,
            worker_config_sha256=control.sha256_bytes(control.encode_config(host.worker_config)),
            receipt=None,
            installed_sha=SHA,
            binding=binding,
            expected_sha=SHA,
        )
        is False
    )
    assert (
        control.ceo_submit_sink_eligible(
            control_config={"ceo_submit_armed": "true"},
            worker_config=host.worker_config,
            worker_config_sha256=control.sha256_bytes(control.encode_config(host.worker_config)),
            receipt=None,
            installed_sha=SHA,
            binding=binding,
            expected_sha=SHA,
        )
        is False
    )
    assert (
        control.ceo_submit_sink_eligible(
            control_config={"ceo_submit_armed": False},
            worker_config=host.worker_config,
            worker_config_sha256=control.sha256_bytes(control.encode_config(host.worker_config)),
            receipt=None,
            installed_sha=SHA,
            binding=binding,
            expected_sha=SHA,
        )
        is False
    )

    # The honest limit is written into the function docstring itself.
    source = Path(control.__file__).read_text(encoding="utf-8")
    docstring = source.split("def ceo_submit_sink_eligible(", 1)[1].split('"""', 2)[1]
    assert "SOURCE-side gate" in docstring
    assert "control_plane/executive_service.py" in docstring
    assert "does not yet consult it" in docstring
    assert "no runtime effect" in docstring


def test_direct_install_with_armed_config_does_not_make_the_ceo_submit_sink_eligible():
    other_sha = "d" * 40
    host = FakeCeoSubmitHost()
    host.installed_sha = other_sha
    host.control_config["proof_base_sha"] = other_sha
    control.execute_ceo_submit_arm(
        host, _ceo_submit_request(expected_sha=other_sha), now=NOW
    )
    binding = host.executive_app_binding()
    postimage = copy.deepcopy(host.control_config)
    receipt = copy.deepcopy(host.receipt)
    assert postimage["ceo_submit_armed"] is True
    assert receipt["projection"]["release_sha"] == other_sha

    assert (
        control.ceo_submit_sink_eligible(
            control_config=postimage,
            worker_config=host.worker_config,
            worker_config_sha256=control.sha256_bytes(control.encode_config(host.worker_config)),
            receipt=receipt,
            installed_sha=other_sha,
            binding=binding,
            expected_sha=other_sha,
        )
        is True
    )
    # The same armed config + the same receipt, but a DIFFERENT release identity.
    assert (
        control.ceo_submit_sink_eligible(
            control_config=postimage, worker_config=host.worker_config, worker_config_sha256=control.sha256_bytes(control.encode_config(host.worker_config)), receipt=receipt, binding=binding, expected_sha=SHA, installed_sha=SHA
        )
        is False
    )

    # A receipt whose projection_digest does not bind the present config.
    tampered = copy.deepcopy(receipt)
    tampered["projection_digest"] = "0" * 64
    assert (
        control.ceo_submit_sink_eligible(
            control_config=postimage,
            worker_config=host.worker_config,
            worker_config_sha256=control.sha256_bytes(control.encode_config(host.worker_config)),
            receipt=tampered,
            installed_sha=other_sha,
            binding=binding,
            expected_sha=other_sha,
        )
        is False
    )
    drifted_config = {**postimage, "ceo_ingress_app_peer_uid": 459}
    assert (
        control.ceo_submit_sink_eligible(
            control_config=drifted_config,
            worker_config=host.worker_config,
            worker_config_sha256=control.sha256_bytes(control.encode_config(host.worker_config)),
            receipt=receipt,
            installed_sha=other_sha,
            binding=binding,
            expected_sha=other_sha,
        )
        is False
    )
    # A projection that is not the closed field set binds nothing.
    assert (
        control.ceo_submit_sink_eligible(
            control_config=postimage,
            worker_config=host.worker_config,
            worker_config_sha256=control.sha256_bytes(control.encode_config(host.worker_config)),
            receipt={**receipt, "projection": {}},
            installed_sha=other_sha,
            binding=binding,
            expected_sha=other_sha,
        )
        is False
    )
    assert (
        control.ceo_submit_sink_eligible(
            control_config=postimage,
            worker_config=host.worker_config,
            worker_config_sha256=control.sha256_bytes(control.encode_config(host.worker_config)),
            receipt={**receipt, "schema_version": "not-the-schema"},
            installed_sha=other_sha,
            binding=binding,
            expected_sha=other_sha,
        )
        is False
    )


def test_only_the_transaction_produced_config_and_receipt_make_the_sink_eligible():
    host = FakeCeoSubmitHost()
    preimage = copy.deepcopy(host.control_config)
    result = control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)
    assert result.state == "CEO_SUBMIT_ARMED"
    binding = host.executive_app_binding()
    postimage = copy.deepcopy(host.control_config)
    receipt = copy.deepcopy(host.receipt)
    assert postimage["ceo_submit_armed"] is True

    assert (
        control.ceo_submit_sink_eligible(
            control_config=postimage, worker_config=host.worker_config, worker_config_sha256=control.sha256_bytes(control.encode_config(host.worker_config)), receipt=receipt, binding=binding, expected_sha=SHA, installed_sha=SHA
        )
        is True
    )

    # Neighbouring states of the very same flow are all ineligible.
    assert (
        control.ceo_submit_sink_eligible(
            control_config=postimage, worker_config=host.worker_config, worker_config_sha256=control.sha256_bytes(control.encode_config(host.worker_config)), receipt=None, binding=binding, expected_sha=SHA, installed_sha=SHA
        )
        is False
    )
    assert (
        control.ceo_submit_sink_eligible(
            control_config=preimage, worker_config=host.worker_config, worker_config_sha256=control.sha256_bytes(control.encode_config(host.worker_config)), receipt=receipt, binding=binding, expected_sha=SHA, installed_sha=SHA
        )
        is False
    )
    assert (
        control.ceo_submit_sink_eligible(
            control_config={**postimage, "ceo_submit_armed": False},
            worker_config=host.worker_config,
            worker_config_sha256=control.sha256_bytes(control.encode_config(host.worker_config)),
            receipt=receipt,
            installed_sha=SHA,
            binding=binding,
            expected_sha=SHA,
        )
        is False
    )
    assert (
        control.ceo_submit_sink_eligible(
            control_config=postimage,
            worker_config=host.worker_config,
            worker_config_sha256=control.sha256_bytes(control.encode_config(host.worker_config)),
            receipt=receipt,
            installed_sha=SHA,
            binding=dataclasses.replace(binding, acl_valid=False),
            expected_sha=SHA,
        )
        is False
    )
    assert (
        control.ceo_submit_sink_eligible(
            control_config=postimage,
            worker_config=host.worker_config,
            worker_config_sha256=control.sha256_bytes(control.encode_config(host.worker_config)),
            receipt=receipt,
            installed_sha=SHA,
            binding=dataclasses.replace(binding, present=False, app_peer_uid=-1),
            expected_sha=SHA,
        )
        is False
    )

    # After a real DISARM the sealed DISARM receipt is not an ARM receipt: the
    # sink must not become eligible again by replaying the closure.
    disarmed = _armed_ceo_submit_host()
    disarm_result = control.execute_ceo_submit_disarm(
        disarmed, _ceo_submit_request(), now=NOW
    )
    assert disarm_result.state == "CEO_SUBMIT_DISARMED"
    assert (
        control.ceo_submit_sink_eligible(
            control_config=disarmed.control_config,
            worker_config=disarmed.worker_config,
            worker_config_sha256=control.sha256_bytes(control.encode_config(disarmed.worker_config)),
            receipt=disarmed.receipt,
            installed_sha=SHA,
            binding=disarmed.executive_app_binding(),
            expected_sha=SHA,
        )
        is False
    )


def test_the_real_submit_ceo_intent_sink_admits_only_the_transaction_produced_state(tmp_path):
    # Mirrors tests/test_chairman_prod_submit.py construction, read-only: this test
    # never edits control_plane/, it only drives the existing service dispatch.
    from control_plane import executive_service
    from control_plane.executive_service import (
        ExecutiveControlService,
        ServiceConfig,
    )

    host = FakeCeoSubmitHost()
    control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)
    binding = host.executive_app_binding()
    postimage = copy.deepcopy(host.control_config)
    receipt = copy.deepcopy(host.receipt)
    assert (
        control.ceo_submit_sink_eligible(
            control_config=postimage, worker_config=host.worker_config, worker_config_sha256=control.sha256_bytes(control.encode_config(host.worker_config)), receipt=receipt, binding=binding, expected_sha=SHA, installed_sha=SHA
        )
        is True
    )

    def _service(*, armed):
        return ExecutiveControlService(
            ServiceConfig(
                runtime_root=tmp_path / "runtime",
                socket_path=executive_service._PRODUCTION_CONTROL_SOCKET,
                proof_source_repository=tmp_path / "source",
                proof_workspace_root=tmp_path / "workspaces",
                proof_base_sha="a" * 40,
                ceo_submit_armed=armed,
            )
        )

    def _request():
        return {
            "version": executive_service.CONTROL_PROTOCOL_VERSION,
            "command": "submit-ceo-intent",
            "args": {"intent": {"intent_id": "w1h3b2-sink-intent"}},
        }

    # The transaction-produced state is admitted by the REAL sink; it is not
    # refused with _CeoSubmitUnarmedError.
    produced = _service(armed=postimage["ceo_submit_armed"])
    assert produced._is_production_control_socket() is True
    produced.runtime = object()
    with mock.patch.object(
        produced, "_submit_service_intent", return_value={"accepted": True}
    ) as handler:
        admitted = asyncio.run(produced._dispatch_request(_request()))
        handler.assert_called_once_with({"intent_id": "w1h3b2-sink-intent"})
    assert admitted == {"accepted": True}

    # An unarmed control config IS refused, and the downstream sink never runs.
    unarmed = _service(armed=False)
    unarmed.runtime = object()
    with mock.patch.object(executive_service.ceo_intent, "submit_intent") as sink:
        with pytest.raises(executive_service._CeoSubmitUnarmedError) as raised:
            asyncio.run(unarmed._dispatch_request(_request()))
        sink.assert_not_called()
    assert raised.value.code == "ceo_submit_unarmed"
    assert str(raised.value) == "CEO intent submission is not armed"

    # HONEST LIMIT, asserted rather than papered over: the service gate consults
    # ONLY the raw boolean, never the sealed receipt.  A hand-edited armed config
    # with no receipt at all is therefore ALSO admitted by the service today, even
    # though the source predicate on that same state is False.  This is the known
    # integration gap owned by a later wave, NOT a defect of this packet; when that
    # wave lands it must invert the `not in source` assertion below in the same PR.
    hand_edited = {"ceo_submit_armed": True}
    hand_service = _service(armed=hand_edited["ceo_submit_armed"])
    hand_service.runtime = object()
    with mock.patch.object(
        hand_service, "_submit_service_intent", return_value={"accepted": True}
    ) as hand_handler:
        hand_admitted = asyncio.run(hand_service._dispatch_request(_request()))
        hand_handler.assert_called_once_with({"intent_id": "w1h3b2-sink-intent"})
    assert hand_admitted == {"accepted": True}
    assert (
        control.ceo_submit_sink_eligible(
            control_config=hand_edited,
            worker_config=host.worker_config,
            worker_config_sha256=control.sha256_bytes(control.encode_config(host.worker_config)),
            receipt=None,
            installed_sha=SHA,
            binding=binding,
            expected_sha=SHA,
        )
        is False
    )
    service_source = Path(executive_service.__file__).read_text(encoding="utf-8")
    assert "ceo_submit_sink_eligible" not in service_source


def test_ceo_submit_reconcile_control_service_can_never_reach_the_worker_boundary(
    monkeypatch,
):
    """R17 B2: the CEO-submit boundary converges control ONLY, never the worker.

    Production shape, no root, no launchd, no network: every argv the module
    would run is captured through the module-level ``subprocess.run``.
    """

    def drive(*, control_loaded: bool) -> list[tuple[list[str], dict[str, object]]]:
        ledger: list[tuple[list[str], dict[str, object]]] = []
        probes = {"count": 0}

        def fake_run(cmd, **kw):
            argv = list(cmd)
            ledger.append((argv, dict(kw)))
            if argv[:2] == ["/bin/launchctl", "print"]:
                probes["count"] += 1
                # A host whose control service is ABSENT answers rc 1 to the
                # first probe and rc 0 to the read-back at the end of the
                # boundary call.
                loaded = control_loaded or probes["count"] > 1
                return mock.Mock(returncode=0 if loaded else 1)
            return mock.Mock(returncode=0)

        monkeypatch.setattr(control.subprocess, "run", fake_run)
        host.reconcile_control_service(SHA)
        return ledger

    def non_probes(ledger):
        return [
            argv
            for argv, _kwargs in ledger
            if argv[:2] != ["/bin/launchctl", "print"]
        ]

    def assert_control_only(ledger):
        joined = "\n".join(" ".join(argv) for argv, _kwargs in ledger)
        assert "service-control.sh" not in joined
        assert control.WORKER_LABEL not in joined
        assert os.fspath(control.WORKER_PLIST) not in joined
        assert "worker" not in joined.lower()
        # Only the argv ledger is inspected: no path under CONFIG_ROOT is named.
        assert os.fspath(control.CONFIG_ROOT) not in joined

    host = control.ProductionCeoSubmitHost()
    assert host._active_transaction is None
    monkeypatch.setattr(
        control.ProductionCeoSubmitHost,
        "_require_control_plist_safe",
        staticmethod(lambda: None),
        raising=False,
    )

    # ABSENT: the control label is not registered, so the boundary bootstraps
    # exactly one fixed control plist and nothing else.
    absent = drive(control_loaded=False)
    assert_control_only(absent)
    assert non_probes(absent) == [
        ["/bin/launchctl", "bootstrap", "system", os.fspath(control.CONTROL_PLIST)]
    ]

    # PRESENT: the control label is loaded, so the boundary kickstarts it. This
    # branch used to raise TypeError before touching launchd because
    # ``_run_fixed`` takes ``cwd`` as a required keyword-only argument.
    present = drive(control_loaded=True)
    assert_control_only(present)
    assert non_probes(present) == [
        ["/bin/launchctl", "kickstart", "-k", f"system/{control.CONTROL_LABEL}"]
    ]

    for ledger in (absent, present):
        for argv, kwargs in ledger:
            if argv[:2] == ["/bin/launchctl", "print"]:
                continue
            assert kwargs.get("cwd") == control.SYSTEM_ROOT / "releases" / SHA
    # No phase was persisted and no manifest write was attempted in either case.
    assert host._active_transaction is None


@pytest.mark.parametrize(
    ("case", "print_results", "expected_argv"),
    [
        (
            "absent_then_still_absent",
            (1,),
            [
                "/bin/launchctl",
                "bootstrap",
                "system",
                os.fspath(control.CONTROL_PLIST),
            ],
        ),
        (
            "present_then_gone",
            (0, 1),
            ["/bin/launchctl", "kickstart", "-k", f"system/{control.CONTROL_LABEL}"],
        ),
    ],
)
def test_ceo_submit_control_boundary_refuses_when_the_launchd_call_does_not_register_control(
    monkeypatch, case, print_results, expected_argv
):
    """A zero exit from ``bootstrap``/``kickstart`` is NOT proof of registration.

    ``launchctl`` can answer 0 while the control label is still absent (the
    bootstrap registered nothing) or has just gone away under a
    ``kickstart -k``.  The boundary must therefore READ BACK the label after the
    call and refuse with ``TransactionEffectUnknown`` when the service is not
    registered.  In both parametrized branches the launchd verb IS attempted and
    the read-back is the only thing that refuses, so a deletion of the read-back
    cannot masquerade as a successful reconcile.

    Production shape, no root, no launchd, no network: every argv the module
    would run is captured through the module-level ``subprocess.run``.
    """

    host = control.ProductionCeoSubmitHost()
    ledger: list[list[str]] = []
    probes = {"count": 0}

    def fake_run(cmd, **kw):
        argv = list(cmd)
        ledger.append(argv)
        if argv[:2] != ["/bin/launchctl", "print"]:
            # bootstrap / kickstart both succeed: a zero exit proves nothing.
            return mock.Mock(returncode=0)
        index = probes["count"]
        probes["count"] += 1
        return mock.Mock(returncode=print_results[min(index, len(print_results) - 1)])

    monkeypatch.setattr(control.subprocess, "run", fake_run)
    monkeypatch.setattr(
        control.ProductionCeoSubmitHost,
        "_require_control_plist_safe",
        staticmethod(lambda: None),
        raising=False,
    )

    with pytest.raises(control.TransactionEffectUnknown):
        host.reconcile_control_service(SHA)

    assert host._active_transaction is None
    verbs = [argv for argv in ledger if argv[:2] != ["/bin/launchctl", "print"]]
    assert verbs == [expected_argv], case
    # The read-back ran strictly AFTER the launchd verb: the refusal is the
    # read-back's, never a skipped call.
    assert ledger.index(expected_argv) < len(ledger) - 1
    assert ledger[-1][:2] == ["/bin/launchctl", "print"]
    assert probes["count"] >= 2


def test_ceo_submit_control_boundary_source_never_names_the_worker_or_the_lifecycle_script():
    source = Path(control.__file__).read_text(encoding="utf-8")
    production = source.split("class ProductionCeoSubmitHost", 1)[1]
    assert "service-control.sh" not in production
    assert production.count("service-control.sh") == 0

    for name in ("def _reconcile_control_boundary", "def reconcile_control_service"):
        body = production.split(name, 1)[1].split("\n    def ", 1)[0]
        assert "WORKER_LABEL" not in body
        assert "WORKER_PLIST" not in body

    boundary = production.split("def _reconcile_control_boundary", 1)[1].split(
        "\n    def ", 1
    )[0]
    for token in (
        "CONTROL_PLIST",
        "CONTROL_LABEL",
        "cwd=release",
        "_require_control_plist_safe",
    ):
        assert token in boundary


class _RollbackProbeHost(control.ProductionCeoSubmitHost):
    """Runs the real rollback body with every OS seam recorded.

    No root, no launchd, no network and no write outside ``tmp_path``: the
    production ``rollback_ceo_submit`` body executes unchanged and every seam
    it reaches (the label probe, the control-only boundary, the CEO-admission
    probe, the phase writer, the receipt writer, the disk re-read and the
    marker removal) answers through this ledger instead of the host OS.

    R80: the rollback now proves the live control service with the SAME
    CEO-admission-bound probe that ARM/DISARM use (see
    ``prove_control_admission_bound``); the recorded seam is the inner
    probe call so the test reads ``("probe", sha, digest)`` and binds to
    the RESTORED preimage's digest.
    """

    def __init__(
        self,
        *,
        loaded=True,
        configs=None,
        reconcile_error=None,
        probe_error=None,
    ):
        super().__init__()
        self.ledger = []
        self._loaded_value = loaded
        self._configs_value = configs
        self._reconcile_error = reconcile_error
        self._probe_error = probe_error

    def _loaded(self, label):
        self.ledger.append(("loaded", label))
        return self._loaded_value

    def _reconcile_control_boundary(self, expected_sha):
        self.ledger.append(("reconcile", expected_sha))
        if self._reconcile_error is not None:
            raise self._reconcile_error

    def _ceo_admission_probe(self, expected_sha, *, candidate_config_digest):
        self.ledger.append(("probe", expected_sha, candidate_config_digest))
        if self._probe_error is not None:
            raise self._probe_error
        return True

    def _persist_phase(self, transaction, phase, *, operation=None):
        self.ledger.append(("phase", phase))

    def write_ceo_submit_receipt(self, transaction, receipt):
        self.ledger.append(("receipt", None))

    def _configs(self):
        self.ledger.append(("configs", None))
        return self._configs_value

    def complete_transaction(self, transaction):
        self.ledger.append(("complete", None))


def _ceo_submit_evidence(*, armed):
    """The control/worker evidence pair, in ``FakeCeoSubmitHost``'s shapes."""

    host = FakeCeoSubmitHost()
    host.control_config["ceo_submit_armed"] = armed
    return control.ConfigEvidence(
        control_sha256=control.sha256_bytes(control.encode_config(host.control_config)),
        worker_sha256=control.sha256_bytes(control.encode_config(host.worker_config)),
        control=copy.deepcopy(host.control_config),
        worker=copy.deepcopy(host.worker_config),
        control_bytes=control.encode_config(host.control_config),
        worker_bytes=control.encode_config(host.worker_config),
    )


def _configs_tuple(evidence):
    """The exact 6-tuple the production ``_configs()`` re-read returns."""

    return (
        copy.deepcopy(dict(evidence.control)),
        copy.deepcopy(dict(evidence.worker)),
        evidence.control_sha256,
        evidence.worker_sha256,
        evidence.control_bytes,
        evidence.worker_bytes,
    )


def _armed_rollback_carrier(prior):
    """The DISARM rollback carrier: the RESTORED preimage, byte-exact.

    ``execute_ceo_submit_disarm`` rebuilds its rollback carrier with
    ``derive_ceo_submit_candidate(prior_configs, armed=True)`` and that call is
    refused by that function's own "already armed" admission guard, so the ARMED
    carrier a rollback carries is assembled here from the identical
    ``CandidateConfigs`` contract: the preimage control/worker pair, re-encoded.
    """

    control_value = copy.deepcopy(dict(prior.control))
    control_value["ceo_submit_armed"] = True
    control_bytes = control.encode_config(control_value)
    return control.CandidateConfigs(
        control=control_value,
        worker=prior.worker,
        control_bytes=control_bytes,
        worker_bytes=prior.worker_bytes,
        control_sha256=control.sha256_bytes(control_bytes),
        worker_sha256=prior.worker_sha256,
    )


def _rollback_transaction(prior, candidates):
    return control.TransactionContext(
        transaction_id="autonomy-9f9f9f9f9f9f",
        expected_sha=SHA,
        prior_configs=prior,
        candidates=candidates,
        admission=None,
    )


def _rollback_probe(monkeypatch, tmp_path, transaction, **host_kwargs):
    """A probe host whose writes land in ``tmp_path`` and are recorded, not made."""

    monkeypatch.setattr(control, "CONFIG_ROOT", tmp_path / "config")
    monkeypatch.setattr(
        control, "CONTROL_CONFIG", tmp_path / "config" / "control.json"
    )
    monkeypatch.setattr(
        control.grp, "getgrnam", lambda name: types.SimpleNamespace(gr_gid=0)
    )
    host_kwargs.setdefault("configs", _configs_tuple(transaction.prior_configs))
    host = _RollbackProbeHost(**host_kwargs)

    def _record_atomic(path, payload, *, mode, uid, gid, replace):
        host.ledger.append(("atomic", path))

    monkeypatch.setattr(control, "_atomic_file", _record_atomic)
    return host


def _rollback_receipt(transaction, *, armed):
    """A minimal rollback receipt: only the shape the probe host records."""

    return {"state": "CEO_SUBMIT_ARMED" if armed else "CEO_SUBMIT_DISARMED"}


def test_ceo_submit_rollback_proves_the_live_control_service_before_removing_the_marker(
    monkeypatch, tmp_path
):
    prior = _ceo_submit_evidence(armed=False)
    transaction = _rollback_transaction(
        prior, control.derive_ceo_submit_candidate(prior, armed=False)
    )
    host = _rollback_probe(monkeypatch, tmp_path, transaction, loaded=True)

    host.rollback_ceo_submit(transaction, _rollback_receipt(transaction, armed=False))

    ledger = [entry for entry in host.ledger if entry[0] != "atomic"]
    probe_digest = prior.control_sha256
    assert ledger == [
        ("receipt", None),
        ("configs", None),
        ("loaded", control.CONTROL_LABEL),
        ("reconcile", SHA),
        ("probe", SHA, probe_digest),
        ("phase", "ADMISSION_BOUND"),
        ("phase", "ROLLBACK_CONTROL_PROVEN"),
        ("complete", None),
    ]
    assert host.ledger[-1] == ("complete", None)
    assert [entry for entry in host.ledger if entry[0] == "atomic"] == [
        ("atomic", control.CONTROL_CONFIG)
    ]
    assert host.ledger.index(("atomic", control.CONTROL_CONFIG)) < host.ledger.index(
        ("complete", None)
    )
    kinds = [entry[0] for entry in ledger]
    assert "reconcile" in kinds
    assert "probe" in kinds
    assert kinds.index("reconcile") < kinds.index("complete")
    assert kinds.index("probe") < kinds.index("complete")

    source = Path(control.__file__).read_text(encoding="utf-8")
    production = source.split("class ProductionCeoSubmitHost", 1)[1]
    body = production.split("def rollback_ceo_submit", 1)[1].split("\n    def ", 1)[0]
    assert "_prove_rolled_back_control_live" in body
    assert body.index("_prove_rolled_back_control_live") < body.index(
        "complete_transaction"
    )
    # R80: the live proof renames ``_await_control_ready`` to the CEO-admission
    # probe and persists the ``ADMISSION_BOUND`` phase rather than the old
    # ``READY_PROVEN``.
    assert "_await_control_ready" not in body
    assert (
        "prove_control_admission_bound" not in body
        or "candidate_config_digest=transaction.prior_configs.control_sha256"
        in body
    )


@pytest.mark.parametrize(
    "failure",
    ["reconcile", "probe"],
)
def test_ceo_submit_rollback_stays_effect_unknown_when_the_live_proof_fails(
    monkeypatch, tmp_path, failure
):
    prior = _ceo_submit_evidence(armed=False)
    transaction = _rollback_transaction(
        prior, control.derive_ceo_submit_candidate(prior, armed=False)
    )
    host = _rollback_probe(
        monkeypatch,
        tmp_path,
        transaction,
        loaded=True,
        **{f"{failure}_error": RuntimeError("boom")},
    )

    with pytest.raises(control.TransactionEffectUnknown):
        host.rollback_ceo_submit(transaction, _rollback_receipt(transaction, armed=False))

    assert ("complete", None) not in host.ledger
    assert ("phase", "ROLLBACK_CONTROL_PROVEN") not in host.ledger
    assert ("reconcile", SHA) in host.ledger
    # The ledger's last entry depends on the failure mode: a reconcile
    # error lands the reconcile tag; a probe error lands the probe tag.
    probe_digest = prior.control_sha256
    if failure == "probe":
        assert host.ledger[-1] == ("probe", SHA, probe_digest)
    else:
        assert host.ledger[-1] == (failure, SHA)


def test_ceo_submit_rollback_needs_no_live_proof_when_no_control_service_is_registered(
    monkeypatch, tmp_path
):
    prior = _ceo_submit_evidence(armed=False)
    transaction = _rollback_transaction(
        prior, control.derive_ceo_submit_candidate(prior, armed=False)
    )
    host = _rollback_probe(monkeypatch, tmp_path, transaction, loaded=False)

    host.rollback_ceo_submit(transaction, _rollback_receipt(transaction, armed=False))

    assert not [entry for entry in host.ledger if entry[0] in {"reconcile", "probe"}]
    assert host.ledger[-1] == ("complete", None)


def test_ceo_submit_rollback_expects_the_restored_preimage_flag_not_a_constant(
    monkeypatch, tmp_path
):
    # (a) DISARM-rollback shape: the restored preimage is the ARMED config.
    armed_prior = _ceo_submit_evidence(armed=True)
    transaction = _rollback_transaction(
        armed_prior, _armed_rollback_carrier(armed_prior)
    )
    host = _rollback_probe(monkeypatch, tmp_path, transaction, loaded=True)

    host.rollback_ceo_submit(transaction, _rollback_receipt(transaction, armed=True))

    assert host.ledger[-1] == ("complete", None)

    # (b) MISMATCH: the disk flag is the OPPOSITE of the restored preimage flag.
    disarmed = _ceo_submit_evidence(armed=False)
    mismatch = _rollback_transaction(armed_prior, _armed_rollback_carrier(armed_prior))
    host = _rollback_probe(
        monkeypatch,
        tmp_path,
        mismatch,
        loaded=True,
        configs=_configs_tuple(disarmed),
    )

    with pytest.raises(control.TransactionEffectUnknown):
        host.rollback_ceo_submit(mismatch, _rollback_receipt(mismatch, armed=True))

    assert ("complete", None) not in host.ledger



def _configs_claiming_the_flag(prior, armed):
    """The probe's disk re-read: ``prior``'s digests, but a chosen arm flag.

    ``rollback_ceo_submit`` compares only the digest STRINGS, so pinning them to
    ``prior``'s leaves the flag comparison as the only thing under test.
    """

    control_value = copy.deepcopy(dict(prior.control))
    control_value["ceo_submit_armed"] = armed
    return (
        control_value,
        copy.deepcopy(dict(prior.worker)),
        prior.control_sha256,
        prior.worker_sha256,
        prior.control_bytes,
        prior.worker_bytes,
    )


@pytest.mark.parametrize(
    "candidate_armed",
    [True, False],
    ids=["arm_rollback", "disarm_rollback"],
)
def test_ceo_submit_rollback_expectation_comes_from_the_rollback_candidate_not_the_preimage(
    monkeypatch, tmp_path, candidate_armed
):
    """The rollback's expected arm bit comes from the ROLLBACK TARGET.

    ``rollback_ceo_submit`` must read its expectation from
    ``transaction.candidates.control`` -- the rollback TARGET -- and never from
    ``transaction.prior_configs.control``.  In the two REAL flows those two
    dicts always agree: an ARM rollback derives its candidate from a disarmed
    preimage (``armed=False``) and a DISARM rollback from an armed preimage
    (``armed=True``).  That makes the distinction invisible to the live suite,
    so this artificial transaction deliberately makes the two flags DIFFER; it
    is the only way to pin WHICH one the code reads.  The intended source is the
    rollback TARGET, so a disk re-read carrying the target's flag must complete
    and one carrying the preimage's flag must be EFFECT_UNKNOWN.
    """

    prior_armed = not candidate_armed
    prior = _ceo_submit_evidence(armed=prior_armed)
    candidates = control.derive_ceo_submit_candidate(prior, armed=candidate_armed)
    assert candidates.control["ceo_submit_armed"] is candidate_armed
    assert prior.control["ceo_submit_armed"] is prior_armed
    transaction = _rollback_transaction(prior, candidates)
    receipt = _rollback_receipt(transaction, armed=candidate_armed)

    # (a) The disk re-read agrees with the rollback TARGET: the rollback completes.
    target_host = _rollback_probe(
        monkeypatch,
        tmp_path,
        transaction,
        loaded=False,
        configs=_configs_claiming_the_flag(prior, candidate_armed),
    )
    target_host.rollback_ceo_submit(transaction, receipt)
    assert target_host.ledger[-1] == ("complete", None)

    # (b) The disk re-read carries the PREIMAGE's flag instead: EFFECT_UNKNOWN,
    # and the marker is never released.
    preimage_host = _rollback_probe(
        monkeypatch,
        tmp_path,
        transaction,
        loaded=False,
        configs=_configs_tuple(prior),
    )
    with pytest.raises(control.TransactionEffectUnknown):
        preimage_host.rollback_ceo_submit(transaction, receipt)
    assert ("complete", None) not in preimage_host.ledger


def _control_plist_stub(mode, *, uid=0, gid=0, nlink=1, error=None):
    class _Stub:
        def lstat(self):
            if error is not None:
                raise error
            return types.SimpleNamespace(
                st_mode=mode, st_uid=uid, st_gid=gid, st_nlink=nlink
            )

    return _Stub()


@pytest.mark.parametrize(
    ("case", "stub_kwargs", "refused"),
    [
        ("regular_root_0644", {"mode": stat.S_IFREG | 0o644}, False),
        ("missing", {"mode": 0, "error": OSError("absent")}, True),
        ("symlink", {"mode": stat.S_IFLNK | 0o777}, True),
        ("not_root_uid", {"mode": stat.S_IFREG | 0o644, "uid": 501}, True),
        ("not_root_gid", {"mode": stat.S_IFREG | 0o644, "gid": 20}, True),
        ("group_writable", {"mode": stat.S_IFREG | 0o664}, True),
        ("other_writable", {"mode": stat.S_IFREG | 0o646}, True),
        ("hard_linked", {"mode": stat.S_IFREG | 0o644, "nlink": 2}, True),
    ],
)
def test_ceo_submit_control_plist_validator_refuses_an_unsafe_bootstrap_target(
    monkeypatch, case, stub_kwargs, refused
):
    monkeypatch.setattr(
        control, "CONTROL_PLIST", _control_plist_stub(**stub_kwargs)
    )
    validator = control.ProductionCeoSubmitHost._require_control_plist_safe
    if refused:
        with pytest.raises(control.TransactionEffectUnknown):
            validator()
    else:
        assert validator() is None


def test_main_routes_only_the_ceo_verbs_to_the_ceo_submit_host_and_leaves_legacy_dispatch_identical(
    capsys,
):
    # (a) BEHAVIOUR.  A legacy COO verb rides the COO transaction host and emits
    # the pre-existing closed documents, byte for byte.
    legacy_arm_argv = [
        "arm",
        "--expected-sha",
        SHA,
        "--gate-b-receipt",
        str(GATE_PATH),
        "--expected-credential-kind",
        "device-auth",
        "--workspace-binding-class",
        "company-workspace-admin-attested",
        "--credential-expires-at",
        "2026-08-25T12:00:00Z",
    ]
    host = FakeTransactionHost()
    arm_result = control.main(legacy_arm_argv, host=host, now=lambda: NOW)
    assert arm_result == 0
    armed = json.loads(capsys.readouterr().out)
    assert armed == {
        "code": "armed",
        "replayed": False,
        "schema_version": control.OPERATION_SCHEMA_VERSION,
        "state": "ARMED",
        "status": "ARMED_READY",
        "transaction_id": "autonomy-deadbeefcafe",
    }
    # The legacy verb ran the COO transaction owner, not a CEO-submit path.
    assert host.transaction_calls == list(FakeTransactionHost.PHASES)
    assert host.marker is False

    host.fail_after = None
    host.transaction_calls.clear()
    disarm_result = control.main(
        ["disarm", "--expected-sha", SHA], host=host, now=lambda: NOW
    )
    assert disarm_result == 0
    disarmed = json.loads(capsys.readouterr().out)
    assert disarmed["code"] == "disarmed"
    assert disarmed["state"] == "DISARMED"
    assert disarmed["status"] == "UNARMED"
    assert disarmed == {
        "code": "disarmed",
        "replayed": False,
        "schema_version": control.OPERATION_SCHEMA_VERSION,
        "state": "DISARMED",
        "status": "UNARMED",
        "transaction_id": "autonomy-deadbeefcafe",
    }
    # Disarm rides the same COO owner and stops before the service phases.
    assert host.transaction_calls == list(FakeTransactionHost.PHASES[:6])

    # (b) SOURCE CONTRACT.  ``main`` names each host exactly once and the CEO host
    # is reachable only inside the ``CEO_SUBMIT_COMMANDS`` branch.
    source = Path(control.__file__).read_text(encoding="utf-8")
    body = source.split("def main(", 1)[1].split("\ndef ", 1)[0]
    assert body.count("ProductionCeoSubmitHost") == 1
    assert body.count("ProductionTransactionHost") == 1
    assert (
        body.index("CEO_SUBMIT_COMMANDS")
        < body.index("ProductionCeoSubmitHost")
        < body.index("ProductionTransactionHost")
    )
    assert "ceo-submit" not in body.split("ProductionTransactionHost", 1)[1]


@pytest.mark.parametrize(
    "verb", ["ceo-submit-status", "ceo-submit-arm", "ceo-submit-disarm"]
)
def test_ceo_submit_cli_is_root_only_with_the_uid_injected_by_the_host(verb, capsys):
    # Root-only is proven by INJECTING the uid through the fake host.  The uid of
    # the process running this suite is never read.
    assert control.require_root_privilege(0) is None
    with pytest.raises(control.HostControlError) as refusal:
        control.require_root_privilege(501)
    assert refusal.value.code == "privilege_required"

    host = FakeCeoSubmitHost(uid=501)
    assert control.main([verb, "--expected-sha", SHA], host=host, now=lambda: NOW) == 2
    document = json.loads(capsys.readouterr().out)
    assert document == {
        "schema_version": control.OPERATION_SCHEMA_VERSION,
        "code": "privilege_required",
        "state": "UNKNOWN",
        "status": "CEO_SUBMIT_UNVERIFIED",
        "transaction_id": None,
        "replayed": False,
    }
    # A refused CLI call writes nothing at all: no candidate, no worker byte, no
    # receipt, no marker and no durable phase.
    assert host.control_writes == 0
    assert host.worker_writes == 0
    assert host.receipt_writes == 0
    assert host.marker is False
    assert host.phases == []


def test_ceo_submit_status_readback_refuses_the_hand_edited_config_shortcut(capsys):
    request = _ceo_submit_request()

    # (a) A disarmed sink reads back DISARMED, with no transaction id.
    disarmed_host = FakeCeoSubmitHost()
    disarmed = control.evaluate_ceo_submit_status(disarmed_host, request)
    assert disarmed == control.TransactionResult(
        state="CEO_SUBMIT_DISARMED",
        status="CEO_SUBMIT_DISARMED",
        transaction_id=None,
        replayed=False,
    )
    assert disarmed_host.control_writes == 0
    assert disarmed_host.receipt_writes == 0
    assert disarmed_host.marker is False
    assert disarmed_host.phases == []

    # (b) A sink armed by a REAL transaction reads back ARMED and reports the
    # SEALED receipt's transaction id.
    armed_host = _armed_ceo_submit_host()
    sealed_transaction_id = armed_host.receipt["transaction_id"]
    assert sealed_transaction_id == "autonomy-feedfacec0de"
    armed_host.reset_ledgers()
    armed = control.evaluate_ceo_submit_status(armed_host, request)
    assert armed == control.TransactionResult(
        state="CEO_SUBMIT_ARMED",
        status="CEO_SUBMIT_ARMED",
        transaction_id=sealed_transaction_id,
        replayed=False,
    )
    assert armed_host.control_writes == 0
    assert armed_host.receipt_writes == 0
    assert armed_host.marker is False
    assert armed_host.phases == []

    # (c) A hand-edited ``ceo_submit_armed: true`` with no sealed receipt is
    # NEVER reported as armed: the manual-config shortcut is refused.
    edited_host = FakeCeoSubmitHost()
    edited_host.control_config["ceo_submit_armed"] = True
    unbound = control.evaluate_ceo_submit_status(edited_host, request)
    assert unbound == control.TransactionResult(
        state="CEO_SUBMIT_ARMED_UNBOUND",
        status="CEO_SUBMIT_ARMED_UNBOUND",
        transaction_id=None,
        replayed=False,
    )
    assert (
        control.main(
            ["ceo-submit-status", "--expected-sha", SHA],
            host=edited_host,
            now=lambda: NOW,
        )
        == 2
    )
    document = json.loads(capsys.readouterr().out)
    assert document == {
        "schema_version": control.OPERATION_SCHEMA_VERSION,
        "code": "ceo_submit_armed_unbound",
        "state": "CEO_SUBMIT_ARMED_UNBOUND",
        "status": "CEO_SUBMIT_ARMED_UNBOUND",
        "transaction_id": None,
        "replayed": False,
    }
    assert edited_host.control_writes == 0
    assert edited_host.receipt_writes == 0
    assert edited_host.marker is False
    assert edited_host.phases == []


def _cli_repository_root() -> Path:
    """Walk up from the module until a directory holding both ``ops``/``tests``."""

    for parent in Path(control.__file__).resolve().parents:
        if (parent / "ops").is_dir() and (parent / "tests").is_dir():
            return parent
    raise AssertionError("cannot locate the repository root for the CLI subprocess")


def test_ceo_submit_cli_subprocess_contract():
    # The REAL module, as a REAL subprocess, under the current NON-ROOT test
    # identity.  No launchd, no root, no network, no writes outside the checkout.
    if os.geteuid() == 0:
        pytest.fail(
            "this contract proof asserts the non-root refusal document; a root "
            "runner would make that assertion meaningless (no skipif is permitted)"
        )

    repo_root = Path(control.__file__).resolve().parents[2]
    # Receipt for the chosen root: it holds this repo's two anchor directories and
    # agrees with the walk-up resolver above.
    assert (repo_root / "ops").is_dir()
    assert (repo_root / "tests").is_dir()
    assert repo_root == _cli_repository_root()

    def _cli(*args):
        return subprocess.run(
            [sys.executable, "-m", "ops.executive_os.autonomy_control", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=60,
            env={
                **os.environ,
                "PYTHONPATH": str(repo_root),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )

    help_run = _cli("--help")
    assert help_run.returncode == 0
    for verb in (
        "status",
        "arm",
        "disarm",
        "ceo-submit-status",
        "ceo-submit-arm",
        "ceo-submit-disarm",
    ):
        assert verb in help_run.stdout

    refusal = {
        "schema_version": control.OPERATION_SCHEMA_VERSION,
        "code": "privilege_required",
        "state": "UNKNOWN",
        "status": "CEO_SUBMIT_UNVERIFIED",
        "transaction_id": None,
        "replayed": False,
    }
    for verb in ("ceo-submit-status", "ceo-submit-arm", "ceo-submit-disarm"):
        run = _cli(verb, "--expected-sha", SHA)
        assert run.returncode == 2
        assert json.loads(run.stdout) == refusal
        assert "Traceback" not in run.stderr

    for bad_sha in ("abc", "F" * 40):
        run = _cli("ceo-submit-status", "--expected-sha", bad_sha)
        assert run.returncode != 0
        assert run.stdout.strip() == ""
        assert "usage:" in run.stderr
        assert "Traceback" not in run.stderr

    coo_flag = _cli(
        "ceo-submit-arm", "--expected-sha", SHA, "--gate-b-receipt", "/tmp/x"
    )
    assert coo_flag.returncode != 0
    assert coo_flag.stdout.strip() == ""
    assert "usage:" in coo_flag.stderr
    assert "Traceback" not in coo_flag.stderr


# ---------------------------------------------------------------------------
# T14 (W1H3R6F): the CEO-submit CLI OUTCOME TABLE.
#
# ``_run_ceo_submit_command`` maps every outcome class to a typed document AND
# an exit code.  Before this test only the ``privilege_required`` refusal path
# (and, incidentally, the hand-edited-config UNBOUND status path) was pinned, so
# ``except TransactionEffectUnknown: exit_code = 2`` could be flipped to ``0``
# with the whole file still green: the subprocess contract test never reaches
# that handler because the root refusal fires first.  Every branch is driven
# here through ``control.main`` and pinned to BOTH its exact parsed JSON
# document and its exact return value.
#
# Root is injected through the fake host's ``effective_uid()``; the uid of the
# process running this suite is never read.
# ---------------------------------------------------------------------------

_CEO_SUBMIT_CLI_ARM = ["ceo-submit-arm", "--expected-sha", SHA]
_CEO_SUBMIT_CLI_DISARM = ["ceo-submit-disarm", "--expected-sha", SHA]
_CEO_SUBMIT_CLI_STATUS = ["ceo-submit-status", "--expected-sha", SHA]
_CEO_SUBMIT_CLI_TRANSACTION_ID = "autonomy-feedfacec0de"


def _ceo_submit_cli_document(code, state, status, transaction_id, replayed=False):
    """The exact operation document, spelled out rather than derived."""

    return {
        "schema_version": control.OPERATION_SCHEMA_VERSION,
        "code": code,
        "state": state,
        "status": status,
        "transaction_id": transaction_id,
        "replayed": replayed,
    }


def _ceo_submit_cli_unverified(code):
    return _ceo_submit_cli_document(
        code, "UNKNOWN", "CEO_SUBMIT_UNVERIFIED", None
    )


def _ceo_submit_cli_effect_unknown():
    return _ceo_submit_cli_document(
        "effect_unknown", "UNKNOWN", "EFFECT_UNKNOWN", None
    )


class _CeoSubmitArmAdmissionRefusingHost(FakeCeoSubmitHost):
    """A CEO-submit host whose config read raises the COO arm-admission type.

    ``_run_ceo_submit_command`` catches ``ArmAdmissionError`` alongside the
    host and CEO-submit admission types because all three ride the one
    ``AUTONOMY_TRANSACTION`` owner; a Protocol-conforming host can raise it.
    """

    def load_ceo_submit_configs(self, expected_sha):
        raise control.ArmAdmissionError("configs_gate_failed")


class _CeoSubmitBoomHost(FakeCeoSubmitHost):
    """A CEO-submit host whose config read raises an UNTYPED error."""

    def load_ceo_submit_configs(self, expected_sha):
        raise RuntimeError("boom")


def _ceo_submit_cli_effect_unknown_host():
    # R9 stickiness: a marker for THIS verb means a prior attempt may already
    # have written, so the callee raises TransactionEffectUnknown before any
    # admission gate -- exactly the handler the R6 finding is about.
    host = FakeCeoSubmitHost()
    host.incomplete_marker_operation = "CEO_SUBMIT_ARM"
    return host


def _ceo_submit_cli_root_refusing_host():
    return FakeCeoSubmitHost(uid=501)


def _ceo_submit_cli_already_armed_host():
    host = _armed_ceo_submit_host()
    # The ARM happened during SETUP; reset the ledgers so the counters describe
    # only the refused ``main`` invocation under test.
    host.reset_ledgers()
    return host


def _ceo_submit_cli_arm_admission_refusing_host():
    return _CeoSubmitArmAdmissionRefusingHost()


def _ceo_submit_cli_rollback_host():
    # A fault after the control-config write with a WORKING rollback becomes
    # ArmTransactionError("arm_rolled_back").
    return FakeCeoSubmitHost(fail_after="control")


def _ceo_submit_cli_boom_host():
    return _CeoSubmitBoomHost()


def _ceo_submit_cli_armed_host():
    return _armed_ceo_submit_host()


def _ceo_submit_cli_disarmed_host():
    return FakeCeoSubmitHost()


def _ceo_submit_cli_disarm_replay_host():
    # A real DISARM transaction first, then a second DISARM is the read-only
    # REPLAY: the sealed receipt keeps its transaction id.
    host = _armed_ceo_submit_host()
    replayed = control.execute_ceo_submit_disarm(
        host, _ceo_submit_request(), now=NOW
    )
    assert replayed.replayed is False
    assert host.control_config["ceo_submit_armed"] is False
    host.reset_ledgers()
    return host


def _ceo_submit_cli_unbound_host():
    host = FakeCeoSubmitHost()
    host.control_config["ceo_submit_armed"] = True
    return host


_CEO_SUBMIT_CLI_OUTCOME_CASES = [
    # -- REFUSALS (exit code 2) --------------------------------------------
    pytest.param(
        _CEO_SUBMIT_CLI_ARM,
        _ceo_submit_cli_effect_unknown_host,
        _ceo_submit_cli_effect_unknown(),
        2,
        True,
        id="refusal_effect_unknown_via_arm_stickiness",
    ),
    pytest.param(
        _CEO_SUBMIT_CLI_STATUS,
        _ceo_submit_cli_effect_unknown_host,
        _ceo_submit_cli_effect_unknown(),
        2,
        True,
        id="refusal_effect_unknown_via_status_stickiness",
    ),
    pytest.param(
        _CEO_SUBMIT_CLI_ARM,
        _ceo_submit_cli_root_refusing_host,
        _ceo_submit_cli_unverified("privilege_required"),
        2,
        True,
        id="refusal_privilege_required",
    ),
    pytest.param(
        _CEO_SUBMIT_CLI_ARM,
        _ceo_submit_cli_already_armed_host,
        _ceo_submit_cli_unverified("ceo_submit_already_armed"),
        2,
        True,
        id="refusal_ceo_submit_admission_already_armed",
    ),
    pytest.param(
        _CEO_SUBMIT_CLI_ARM,
        _ceo_submit_cli_arm_admission_refusing_host,
        _ceo_submit_cli_unverified("configs_gate_failed"),
        2,
        True,
        id="refusal_arm_admission_error",
    ),
    pytest.param(
        _CEO_SUBMIT_CLI_ARM,
        _ceo_submit_cli_rollback_host,
        _ceo_submit_cli_unverified("arm_rolled_back"),
        2,
        False,
        id="refusal_arm_transaction_rolled_back",
    ),
    pytest.param(
        _CEO_SUBMIT_CLI_ARM,
        _ceo_submit_cli_boom_host,
        _ceo_submit_cli_effect_unknown(),
        2,
        True,
        id="refusal_untyped_runtime_error_catch_all",
    ),
    # -- SUCCESS PATHS -----------------------------------------------------
    pytest.param(
        _CEO_SUBMIT_CLI_ARM,
        _ceo_submit_cli_disarmed_host,
        _ceo_submit_cli_document(
            "ceo_submit_armed",
            "CEO_SUBMIT_ARMED",
            "CEO_SUBMIT_ARMED",
            _CEO_SUBMIT_CLI_TRANSACTION_ID,
        ),
        0,
        False,
        id="success_arm",
    ),
    pytest.param(
        _CEO_SUBMIT_CLI_DISARM,
        _ceo_submit_cli_armed_host,
        _ceo_submit_cli_document(
            "ceo_submit_disarmed",
            "CEO_SUBMIT_DISARMED",
            "CEO_SUBMIT_DISARMED",
            _CEO_SUBMIT_CLI_TRANSACTION_ID,
        ),
        0,
        False,
        id="success_disarm",
    ),
    pytest.param(
        _CEO_SUBMIT_CLI_DISARM,
        _ceo_submit_cli_disarm_replay_host,
        _ceo_submit_cli_document(
            "ceo_submit_already_disarmed",
            "CEO_SUBMIT_DISARMED",
            "CEO_SUBMIT_DISARMED",
            _CEO_SUBMIT_CLI_TRANSACTION_ID,
            replayed=True,
        ),
        0,
        False,
        id="success_disarm_replayed",
    ),
    pytest.param(
        _CEO_SUBMIT_CLI_STATUS,
        _ceo_submit_cli_disarmed_host,
        _ceo_submit_cli_document(
            "ceo_submit_disarmed",
            "CEO_SUBMIT_DISARMED",
            "CEO_SUBMIT_DISARMED",
            None,
        ),
        0,
        False,
        id="success_status_disarmed",
    ),
    pytest.param(
        _CEO_SUBMIT_CLI_STATUS,
        _ceo_submit_cli_armed_host,
        _ceo_submit_cli_document(
            "ceo_submit_armed",
            "CEO_SUBMIT_ARMED",
            "CEO_SUBMIT_ARMED",
            _CEO_SUBMIT_CLI_TRANSACTION_ID,
        ),
        0,
        False,
        id="success_status_armed_and_bound",
    ),
    pytest.param(
        _CEO_SUBMIT_CLI_STATUS,
        _ceo_submit_cli_unbound_host,
        _ceo_submit_cli_document(
            "ceo_submit_armed_unbound",
            "CEO_SUBMIT_ARMED_UNBOUND",
            "CEO_SUBMIT_ARMED_UNBOUND",
            None,
        ),
        2,
        True,
        id="refusal_status_armed_but_unbound",
    ),
]


@pytest.mark.parametrize(
    "argv, build_host, expected_document, expected_exit, refusal_writes_nothing",
    _CEO_SUBMIT_CLI_OUTCOME_CASES,
)
def test_ceo_submit_cli_pins_every_outcome_class_document_and_exit_code(
    argv, build_host, expected_document, expected_exit, refusal_writes_nothing,
    capsys,
):
    host = build_host()
    result = control.main(list(argv), host=host, now=lambda: NOW)
    captured = capsys.readouterr()

    # EXACT exit code for this outcome class.
    assert result == expected_exit

    # EXACTLY one line of JSON on stdout, no traceback text anywhere.
    assert captured.out.endswith("\n")
    assert captured.out.count("\n") == 1
    lines = captured.out.splitlines()
    assert len(lines) == 1
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err
    assert captured.err == ""

    # EXACT document, byte-for-byte in canonical form.
    document = json.loads(lines[0])
    assert document == expected_document
    assert set(document) == {
        "schema_version",
        "code",
        "state",
        "status",
        "transaction_id",
        "replayed",
    }
    assert lines[0] == json.dumps(
        expected_document, sort_keys=True, separators=(",", ":")
    )

    if expected_exit != 0:
        # No refusal may leave a transaction marker behind.
        assert host.marker is False
        # ...and the refusals that stop BEFORE the lock write nothing at all.
        # (The rollback refusal is the one class that legitimately entered the
        # transaction before its typed refusal; its restored state is pinned by
        # the dedicated rollback tests.)
        if refusal_writes_nothing:
            assert host.control_writes == 0
            assert host.worker_writes == 0
            assert host.worker_replace_calls == 0
            assert host.receipt_writes == 0
            assert host.phases == []


# ---------------------------------------------------------------------------
# R7 / R80 coverage: the REAL CEO-admission poll and the candidate-path
# contract.
#
# ``ProductionCeoSubmitHost._await_control_admission_bound`` is the single
# CEO-admission seam behind BOTH ``prove_control_admission_bound`` (the
# ARM/DISARM CEO-admission proof) and ``_prove_rolled_back_control_live``
# (the R17 B3 / R80 live rollback proof).  The rollback tests above override
# the inner probe seam on a probe subclass, so before these tests the real
# loop had no behavioural coverage at all.  These tests drive the real method
# over a recorded subclass with a deterministic fake clock -- no sleeping,
# no wall clock, no root, no launchd and no network.
# ---------------------------------------------------------------------------


class _FakeMonotonic:
    """A deterministic ``time.monotonic``: one fixed step per read."""

    def __init__(self, *, start=1000.0, step=1.0):
        self._current = start
        self._step = step
        self.calls = 0

    def __call__(self):
        self.calls += 1
        value = self._current
        self._current += self._step
        return value


class _SleepRecorder:
    """The fake ``time.sleep``: records the request and never waits."""

    def __init__(self):
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)


def _install_fake_clock(monkeypatch):
    """Install the deterministic clock pair, returning ``(clock, sleeps)``."""

    clock = _FakeMonotonic()
    sleeps = _SleepRecorder()
    monkeypatch.setattr(control.time, "monotonic", clock)
    monkeypatch.setattr(control.time, "sleep", sleeps)
    return clock, sleeps


class _AdmissionProbeHost(control.ProductionCeoSubmitHost):
    """The real CEO-admission poll with every OS seam recorded and none reached.

    R80: ``_loaded`` always answers True, ``_ceo_admission_probe`` answers
    False for the first ``ready_after - 1`` polls and True on the
    ``ready_after``-th (never, when ``ready_after`` is None), and
    ``_persist_phase`` records.  The probe seam is the new one
    ``_await_control_admission_bound`` polls.
    """

    def __init__(self, *, ready_after=None):
        super().__init__()
        self.ledger = []
        self.ready_calls = 0
        self.last_digest = None
        self._ready_after = ready_after

    def _loaded(self, label):
        self.ledger.append(("loaded", label))
        return True

    def _ceo_admission_probe(self, expected_sha, *, candidate_config_digest):
        self.ready_calls += 1
        self.ledger.append(("probe", expected_sha, candidate_config_digest))
        self.last_digest = candidate_config_digest
        if self._ready_after is None:
            return False
        return self.ready_calls >= self._ready_after

    def _persist_phase(self, transaction, phase, *, operation=None):
        self.ledger.append(("phase", phase))


def _readiness_transaction():
    """A carrier for the phase writer; the probe host never reads its fields."""

    return control.TransactionContext(
        transaction_id="autonomy-0123456789ab",
        expected_sha=SHA,
        prior_configs=None,
        candidates=None,
        admission=None,
    )


def test_ceo_submit_control_admission_bound_polls_until_ready_and_raises_only_after_the_deadline(
    monkeypatch,
):
    # R80: the CEO ARM/DISARM readiness stage is now the CEO-admission proof.
    candidate_digest = "f" * 64
    # (a) ADMITTED ON THE THIRD POLL: the method must actually POLL, then return.
    _clock, sleeps = _install_fake_clock(monkeypatch)
    third_poll = _AdmissionProbeHost(ready_after=3)

    assert (
        third_poll._await_control_admission_bound(
            SHA, candidate_config_digest=candidate_digest
        )
        is None
    )

    assert third_poll.ledger.count(("probe", SHA, candidate_digest)) == 3
    assert third_poll.ready_calls == 3
    assert third_poll.last_digest == candidate_digest
    assert len(sleeps.calls) == 2
    # The label probe runs inside the poll, and only on the control boundary.
    assert third_poll.ledger.count(("loaded", control.CONTROL_LABEL)) == 3
    assert third_poll.ledger.count(("loaded", control.WORKER_LABEL)) == 0

    # (b) ADMITTED IMMEDIATELY: one poll and not one sleep.
    _clock, sleeps = _install_fake_clock(monkeypatch)
    immediate = _AdmissionProbeHost(ready_after=1)

    assert (
        immediate._await_control_admission_bound(
            SHA, candidate_config_digest=candidate_digest
        )
        is None
    )

    assert immediate.ledger.count(("probe", SHA, candidate_digest)) == 1
    assert immediate.ready_calls == 1
    assert sleeps.calls == []

    # (c) NEVER ADMITTED: the deadline ends the loop, and it ends LOOPING.
    clock, sleeps = _install_fake_clock(monkeypatch)
    never = _AdmissionProbeHost(ready_after=None)

    with pytest.raises(RuntimeError) as raised:
        never._await_control_admission_bound(
            SHA, candidate_config_digest=candidate_digest
        )

    assert "did not bind" in str(raised.value)
    assert "ADMISSION" in str(raised.value).upper() or "admission" in str(raised.value)
    assert not isinstance(raised.value, control.TransactionEffectUnknown)
    # Bounded: the fake clock advances 1.0s per read against a 45.0s budget, so
    # a poll that keeps re-reading the clock can never exceed 46 body passes.
    assert 1 < never.ready_calls <= 46
    assert clock.calls > never.ready_calls
    assert len(sleeps.calls) >= 1

    # ``prove_control_admission_bound`` DELEGATES: the phase is persisted
    # exactly once, AFTER the probe returned, and only inside a transaction.
    _clock, sleeps = _install_fake_clock(monkeypatch)
    bound = _AdmissionProbeHost(ready_after=2)
    bound._active_transaction = _readiness_transaction()

    assert (
        bound.prove_control_admission_bound(
            SHA, candidate_config_digest=candidate_digest
        )
        is None
    )

    ready_positions = [
        index
        for index, entry in enumerate(bound.ledger)
        if entry[0] == "probe"
    ]
    assert bound.ledger.count(("phase", "ADMISSION_BOUND")) == 1
    assert ready_positions
    assert max(ready_positions) < bound.ledger.index(("phase", "ADMISSION_BOUND"))
    assert len(sleeps.calls) == 1

    _clock, _sleeps = _install_fake_clock(monkeypatch)
    unbound = _AdmissionProbeHost(ready_after=1)
    unbound._active_transaction = None

    assert (
        unbound.prove_control_admission_bound(
            SHA, candidate_config_digest=candidate_digest
        )
        is None
    )

    assert unbound.ledger.count(("probe", SHA, candidate_digest)) == 1
    assert all(entry[0] != "phase" for entry in unbound.ledger)


def test_ceo_submit_candidate_paths_are_distinct_and_returned_control_first():
    host = control.ProductionCeoSubmitHost()

    control_candidate, worker_candidate = host._candidate_paths(
        "autonomy-0123456789ab"
    )

    # Two DISTINCT staging paths, control FIRST: the pair is consumed in order,
    # so a swap silently renames which boundary is named first.
    assert control_candidate != worker_candidate
    assert control_candidate.name == ".autonomy-control-0123456789ab.candidate.json"
    assert worker_candidate.name == ".autonomy-worker-0123456789ab.candidate.json"
    assert "control" in control_candidate.name
    assert "worker" in worker_candidate.name
    assert "worker" not in control_candidate.name
    assert "control" not in worker_candidate.name

    # Both stage DIRECTLY beside the installed configs they replace.
    for candidate in (control_candidate, worker_candidate):
        assert candidate.parent == control.CONFIG_ROOT
        assert candidate.name.startswith(".")
        assert candidate.name.endswith(".candidate.json")

    # A transaction id outside the closed ``autonomy-[0-9a-f]{12}`` domain is
    # EFFECT_UNKNOWN, never a path derived from arbitrary caller text.
    for rejected in ("autonomy-XYZ", "nope", ""):
        with pytest.raises(control.TransactionEffectUnknown):
            host._candidate_paths(rejected)


def _drift_armed_ceo_submit_host():
    """A really-armed host whose live App binding can then be drifted one fact at a time.

    The ARM seals a receipt from the UNDRIFTED binding; mutating
    ``binding_overrides`` afterwards changes only what ``executive_app_binding()``
    reports live.  The status assertion here is the positive control: it proves
    the fixture truly reached CEO_SUBMIT_ARMED before any drift, so a later
    CEO_SUBMIT_ARMED_UNBOUND is the drift and not a broken fixture.
    """

    host = _armed_ceo_submit_host()
    assert (
        control.evaluate_ceo_submit_status(host, _ceo_submit_request()).state
        == "CEO_SUBMIT_ARMED"
    )
    host.reset_ledgers()
    return host


_CEO_SUBMIT_LIVE_BINDING_DRIFT = [
    ("app_peer_uid", 459),
    ("ingress_peer_uid", 453),
    # R68: the post-ARM App drift the contract names is TRUE->FALSE
    # (the live transport was lost while the control still says armed),
    # not a True->True override that the helper cannot distinguish from a
    # fixture no-op.  The marker is True (control still says armed), the
    # binding override is False (live transport lost), the six-fact
    # comparison fails, and status reads back ARMED_UNBOUND.
    ("app_armed", False),
    ("app_macro_root", "/fixture/changed-macro"),
    ("ingress_socket_path", "/fixture/changed-ingress.sock"),
    ("launchd_socket_name", "ChangedIngress"),
]


# Maps each live-binding field to its CONTROL config counterpart.  The
# fake's binding reads the control's value by default (so ARM's R76
# six-fact check passes), which means a binding-only override is
# ABSORBED by the next sync read.  True drift requires both the live
# override AND a DIFFERENT control value.
_DRIFT_CONTROL_COUNTERPART = {
    "app_peer_uid": ("ceo_ingress_app_peer_uid", int, 458),
    "ingress_peer_uid": ("ceo_ingress_peer_uid", int, 452),
    "app_armed": ("ceo_ingress_app_armed", bool, True),
    "app_macro_root": (
        "ceo_ingress_app_macro_root",
        str,
        "drift-marker-app_macro_root",
    ),
    "ingress_socket_path": (
        "ceo_ingress_socket_path",
        str,
        "drift-marker-ingress_socket_path",
    ),
    "launchd_socket_name": (
        "ceo_ingress_launchd_socket_name",
        str,
        "drift-marker-launchd_socket_name",
    ),
}


def _drift_one_field(host, field, value):
    """Drift exactly one fact: live binding overridden, control at a marker."""

    control_field, _kind, marker = _DRIFT_CONTROL_COUNTERPART[field]
    host.binding_overrides[field] = value
    # Keep the control's value DIFFERENT from the binding override by
    # pinning it to a marker that the ``_ceo_submit_binding_matches_control``
    # comparison is guaranteed NOT to match.
    host.control_config[control_field] = marker


@pytest.mark.parametrize("field,value", _CEO_SUBMIT_LIVE_BINDING_DRIFT)
def test_status_rejects_each_live_binding_identity_drift(field, value):
    host = _drift_armed_ceo_submit_host()
    _drift_one_field(host, field, value)
    result = control.evaluate_ceo_submit_status(host, _ceo_submit_request())
    assert result.state == "CEO_SUBMIT_ARMED_UNBOUND"
    assert host.control_writes == host.worker_writes == host.receipt_writes == 0


def test_unchanged_binding_remains_armed_without_writes():
    host = _drift_armed_ceo_submit_host()
    assert (
        control.evaluate_ceo_submit_status(host, _ceo_submit_request()).state
        == "CEO_SUBMIT_ARMED"
    )
    assert host.control_writes == host.worker_writes == host.receipt_writes == 0


@pytest.mark.parametrize("field", ["binding_valid", "acl_valid", "topology_valid"])
def test_existing_negative_binding_flags_are_still_refused(field):
    host = _drift_armed_ceo_submit_host()
    host.binding_overrides[field] = False
    assert (
        control.evaluate_ceo_submit_status(host, _ceo_submit_request()).state
        == "CEO_SUBMIT_ARMED_UNBOUND"
    )


@pytest.mark.parametrize("field,value", _CEO_SUBMIT_LIVE_BINDING_DRIFT)
def test_cli_status_does_not_report_ready_after_live_binding_drift(field, value, capsys):
    host = _drift_armed_ceo_submit_host()
    host.binding_overrides[field] = value
    code = control.main(
        ["ceo-submit-status", "--expected-sha", SHA], host=host, now=lambda: NOW
    )
    output = capsys.readouterr()
    assert code == 2
    document = json.loads(output.out)
    assert document["state"] == "CEO_SUBMIT_ARMED_UNBOUND"
    assert output.err == ""
    assert host.control_writes == host.worker_writes == host.receipt_writes == 0
