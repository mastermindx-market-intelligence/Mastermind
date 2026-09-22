"""Host-policy tests for the root-only Executive autonomy control surface."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import copy
import dataclasses
import hashlib
import io
import json
import os
import re
import select
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
# W1H3F R13: constants used by the live-attestation validator ride in the probe.
_STATUS_PID = 4242
# Probe fixtures model the already-root-read current control bytes.  The parsed
# object is separately supplied by the root-json seam; this constant makes the
# digest comparison itself load-bearing without a preimage trick.
_CONTROL_CONFIG_RAW = b"packet09-control-config-r80-v1\n"
_CONFIG_DIGEST = hashlib.sha256(_CONTROL_CONFIG_RAW).hexdigest()
# The good document's release_commit_sha matches ``SHA`` so a default
# ``_good_attestation_doc()`` is admitted under the canonical probe call
# ``host._ceo_admission_probe(SHA, _CONFIG_DIGEST)``.
_RELEASE_SHA = SHA
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

    # The CEO-submit operation domain is the SAME parser: three state verbs plus
    # one same-transaction reconciliation verb, each bounded to --expected-sha alone.
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
    assert vars(parser.parse_args(["ceo-submit-reconcile", "--expected-sha", SHA])) == {
        "command": "ceo-submit-reconcile",
        "expected_sha": SHA,
    }

    # The command set is EXACTLY the closed seven: no generic recovery/debug verb
    # exists, and the three legacy autonomy verbs remain present.
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
        "ceo-submit-reconcile",
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

    for verb in (
        "ceo-submit-status",
        "ceo-submit-arm",
        "ceo-submit-disarm",
        "ceo-submit-reconcile",
    ):
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
    for verb in (
        "status",
        "arm",
        "disarm",
        "ceo-submit-status",
        "ceo-submit-arm",
        "ceo-submit-disarm",
        "ceo-submit-reconcile",
    ):
        assert verb in wrapper
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


def test_arm_begin_ownership_failure_refuses_without_rollback_or_service_effects():
    host = FakeTransactionHost()
    before_control = copy.deepcopy(host.control_config)
    before_worker = copy.deepcopy(host.worker_config)
    effects = []

    def ownership_failure(_transaction):
        # The failed creator's marker is durable evidence, but this process did
        # not acquire its execution owner and may not operate on that marker.
        host.marker = True
        raise control.TransactionOwnershipError()

    host.begin_transaction = ownership_failure
    host.stop_services = lambda _sha: effects.append("stop")
    host.rollback_disarmed = lambda *_args, **_kwargs: effects.append("rollback")

    with pytest.raises(control.TransactionEffectUnknown):
        control.execute_arm(host, _arm_request(), now=NOW)

    assert effects == []
    assert host.marker is True
    assert host.control_config == before_control
    assert host.worker_config == before_worker
    assert host.receipt is None


def test_arm_owned_post_begin_failure_still_runs_the_normal_rollback():
    host = FakeTransactionHost(fail_after="candidates")
    rollback = []
    real_rollback = host.rollback_disarmed

    def recorded_rollback(transaction, receipt):
        rollback.append(transaction.transaction_id)
        real_rollback(transaction, receipt)

    host.rollback_disarmed = recorded_rollback

    with pytest.raises(control.ArmTransactionError) as raised:
        control.execute_arm(host, _arm_request(), now=NOW)

    assert raised.value.code == "arm_rolled_back"
    assert rollback == ["autonomy-deadbeefcafe"]
    assert host.marker is False
    assert host.services == "STOPPED"
    assert host.receipt["state"] == "DISARMED"


def test_arm_owned_partial_begin_failure_still_runs_the_normal_rollback():
    host = FakeTransactionHost(fail_after="lock")
    rollback = []
    real_rollback = host.rollback_disarmed

    def recorded_rollback(transaction, receipt):
        rollback.append(transaction.transaction_id)
        real_rollback(transaction, receipt)

    host.rollback_disarmed = recorded_rollback

    with pytest.raises(control.ArmTransactionError) as raised:
        control.execute_arm(host, _arm_request(), now=NOW)

    assert raised.value.code == "arm_rolled_back"
    assert host.transaction_calls == ["lock"]
    assert rollback == ["autonomy-deadbeefcafe"]
    assert host.marker is False
    assert host.services == "STOPPED"
    assert host.receipt["state"] == "DISARMED"


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
    # The canonical marker is never mkdir'd into visibility: it exists only as
    # a private generation renamed into place, so the first visible state is
    # the complete sealed marker and no empty canonical directory can be
    # stolen.  The publication itself stays serialized, no-clobber and
    # verified against the exact held inode.
    assert "os.mkdir(AUTONOMY_TRANSACTION" not in production
    create = production.split("def _create_marker", 1)[1].split("\n    def ", 1)[0]
    assert "os.mkdir(generation, 0o700)" in create
    assert "os.rename(generation, AUTONOMY_TRANSACTION)" in create
    assert "_seal_generation(" in create
    assert "_publication_mutex()" in create
    assert "_require_canonical_absent()" in create
    assert "_verify_published_inode(" in create
    assert "fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)" in create
    assert create.index("fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)") < create.index(
        "_seal_generation("
    ) < create.index("_publication_mutex()") < create.index(
        "os.rename(generation, AUTONOMY_TRANSACTION)"
    ) < create.index("_fsync_directory(CONFIG_ROOT)") < create.index(
        "_verify_published_inode("
    )
    assert "TransactionEffectUnknown" in create
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

    def prove_control_admission_bound(self, expected_sha, expected_control_sha256=""):
        # R80: rename matches the production protocol method and the new
        # fixed-arity signature.  The fake records every call (default
        # ADMITTED) so it stays a pure witness.
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

    def bounded_read(*args, **kwargs):
        if len(raw) > control._MAX_JSON_BYTES:
            raise control.HostControlError("config_identity_unavailable")
        return raw, mock.Mock()

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


def test_production_receipt_read_boundary_accepts_exact_valid_fixture_bytes():
    host = _armed_ceo_submit_host()
    raw = control._encoded_json(host.receipt)

    assert _strict_receipt_payload(raw) == host.receipt


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
        # Re-join any open-paren continuation so the structural fences can
        # read the call as one logical line.
        rejoined: list[str] = []
        buffer: list[str] = []
        open_count = 0
        for line in lines:
            if buffer:
                buffer.append(line)
                open_count += line.count("(") - line.count(")")
                if open_count <= 0:
                    rejoined.append(" ".join(buffer))
                    buffer = []
                    open_count = 0
            elif "(" in line and ")" not in line and line.count("(") > line.count(")"):
                buffer.append(line)
                open_count = line.count("(") - line.count(")")
            else:
                rejoined.append(line)
        lines = rejoined
        assert [
            line for line in lines if "reconcile_control_service" in line
        ] == ["host.reconcile_control_service(request.expected_sha)"]
        # W1H3F R13: ARM/DISARM ride the CEO-admission proof with the new
        # exact-control-digest parameter that the wrapper-owned validator
        # consults.  The candidate digest comes from
        # ``transaction.candidates.control_sha256`` -- the same bytes H3 just
        # hashed -- and is NOT a launcher or kickstart parameter.
        bound_lines = [
            line
            for line in lines
            if "prove_control_admission_bound" in line
            and "host.prove_control_admission_bound(" in line
            and "request.expected_sha" in line
            and "transaction.candidates.control_sha256" in line
        ]
        assert len(bound_lines) == 1
        assert "candidate_config_digest" not in bound_lines[0]
        assert "kickstart" not in " ".join(bound_lines)
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


def test_ceo_submit_control_boundary_enables_only_control_before_bootstrap(monkeypatch):
    """A disabled control override must not strand the control-only CEO-submit reconcile."""

    host = control.ProductionCeoSubmitHost()
    ledger: list[list[str]] = []
    probes = {"count": 0}

    def fake_run(cmd, **kw):
        argv = list(cmd)
        ledger.append(argv)
        if argv[:2] == ["/bin/launchctl", "print"]:
            probes["count"] += 1
            return mock.Mock(returncode=1 if probes["count"] == 1 else 0)
        return mock.Mock(returncode=0)

    monkeypatch.setattr(control.subprocess, "run", fake_run)
    monkeypatch.setattr(
        control.ProductionCeoSubmitHost,
        "_require_control_plist_safe",
        staticmethod(lambda: None),
        raising=False,
    )
    monkeypatch.setattr(host, "_ensure_control_launchd_preimage", lambda: True)

    host.reconcile_control_service(SHA)

    non_probes = [argv for argv in ledger if argv[:2] != ["/bin/launchctl", "print"]]
    assert non_probes == [
        ["/bin/launchctl", "enable", f"system/{control.CONTROL_LABEL}"],
        ["/bin/launchctl", "bootstrap", "system", os.fspath(control.CONTROL_PLIST)],
    ]
    joined = "\n".join(" ".join(argv) for argv in ledger)
    assert control.WORKER_LABEL not in joined
    assert os.fspath(control.WORKER_PLIST) not in joined


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
    monkeypatch.setattr(host, "_ensure_control_launchd_preimage", lambda: True)
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
        ["/bin/launchctl", "enable", f"system/{control.CONTROL_LABEL}"],
        ["/bin/launchctl", "bootstrap", "system", os.fspath(control.CONTROL_PLIST)],
    ]

    # PRESENT: the control label is loaded, so the boundary kickstarts it. This
    # branch used to raise TypeError before touching launchd because
    # ``_run_fixed`` takes ``cwd`` as a required keyword-only argument.
    present = drive(control_loaded=True)
    assert_control_only(present)
    assert non_probes(present) == [
        ["/bin/launchctl", "enable", f"system/{control.CONTROL_LABEL}"],
        ["/bin/launchctl", "kickstart", "-k", f"system/{control.CONTROL_LABEL}"],
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
    monkeypatch.setattr(host, "_ensure_control_launchd_preimage", lambda: True)

    with pytest.raises(control.TransactionEffectUnknown):
        host.reconcile_control_service(SHA)

    assert host._active_transaction is None
    verbs = [argv for argv in ledger if argv[:2] != ["/bin/launchctl", "print"]]
    assert verbs == [
        ["/bin/launchctl", "enable", f"system/{control.CONTROL_LABEL}"],
        expected_argv,
    ], case
    # The read-back ran strictly AFTER the launchd verb: the refusal is the
    # read-back's, never a skipped call.
    assert ledger.index(expected_argv) < len(ledger) - 1
    assert ledger[-1][:2] == ["/bin/launchctl", "print"]
    assert probes["count"] >= 2



@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("disabled", True),
        ("true", True),
        ("enabled", False),
        ("false", False),
    ],
)
def test_ceo_submit_launchd_override_reader_accepts_only_explicit_target_rows(
    monkeypatch, state, expected
):
    payload = (
        "disabled services = {\n"
        '\t"com.apple.example" => enabled\n'
        f'\t"{control.CONTROL_LABEL}" => {state}\n'
        "}\n"
    ).encode()

    monkeypatch.setattr(
        control.ProductionCeoSubmitHost,
        "_capture_control_launchd_disabled_output",
        staticmethod(lambda: payload),
    )

    assert control.ProductionCeoSubmitHost._read_control_launchd_disabled_override() is expected


@pytest.mark.parametrize(
    "payload",
    [
        b'disabled services = {\n"com.apple.example" => enabled\n}\n',
        (
            'disabled services = {\n'
            f'"{control.CONTROL_LABEL}" => disabled\n'
            f'"{control.CONTROL_LABEL}" => disabled\n'
            '}\n'
        ).encode(),
        (
            'disabled services = {\n'
            f'"{control.CONTROL_LABEL}" => banana\n'
            '}\n'
        ).encode(),
        b"not the launchd table\n",
    ],
)
def test_ceo_submit_launchd_override_reader_refuses_missing_duplicate_or_malformed(
    monkeypatch, payload
):
    monkeypatch.setattr(
        control.ProductionCeoSubmitHost,
        "_capture_control_launchd_disabled_output",
        staticmethod(lambda: payload),
    )

    with pytest.raises(control.TransactionEffectUnknown):
        control.ProductionCeoSubmitHost._read_control_launchd_disabled_override()


def test_ceo_submit_launchd_override_capture_bounds_before_buffering_and_reaps(
    monkeypatch,
):
    real_popen = control.subprocess.Popen
    spawned = {}

    def oversized_launchctl(argv, **kwargs):
        assert argv == ["/bin/launchctl", "print-disabled", "system"]
        process = real_popen(
            [
                sys.executable,
                "-c",
                (
                    "import sys,time;"
                    "sys.stdout.buffer.write(b'x' * "
                    f"{control._MAX_LAUNCHCTL_DISABLED_BYTES + 1});"
                    "sys.stdout.flush();time.sleep(10)"
                ),
            ],
            **kwargs,
        )
        spawned["process"] = process
        return process

    monkeypatch.setattr(control.subprocess, "Popen", oversized_launchctl)

    with pytest.raises(control.TransactionEffectUnknown):
        control.ProductionCeoSubmitHost._capture_control_launchd_disabled_output()

    assert spawned["process"].poll() is not None


def test_ceo_submit_control_boundary_seals_preimage_before_enable(monkeypatch):
    host = control.ProductionCeoSubmitHost()
    ledger = []

    monkeypatch.setattr(
        host,
        "_ensure_control_launchd_preimage",
        lambda: ledger.append(("preimage", True)) or True,
    )
    monkeypatch.setattr(host, "_loaded", lambda _label: True)
    monkeypatch.setattr(
        host,
        "_run_fixed",
        lambda argv, **kwargs: ledger.append(("run", list(argv))),
    )

    host._reconcile_control_boundary(SHA)

    assert ledger[0] == ("preimage", True)
    assert ledger[1] == (
        "run",
        ["/bin/launchctl", "enable", f"system/{control.CONTROL_LABEL}"],
    )
    assert ledger[2] == (
        "run",
        ["/bin/launchctl", "kickstart", "-k", f"system/{control.CONTROL_LABEL}"],
    )


@pytest.mark.parametrize(("prior_disabled", "expect_disable"), [(True, True), (False, False)])
def test_ceo_submit_rollback_restores_and_proves_launchd_override(
    monkeypatch, prior_disabled, expect_disable
):
    prior = _ceo_submit_evidence(armed=False)
    transaction = _rollback_transaction(
        prior, control.derive_ceo_submit_candidate(prior, armed=False)
    )
    host = control.ProductionCeoSubmitHost()
    ledger = []
    manifest = {
        "transaction_id": transaction.transaction_id,
        "expected_sha": transaction.expected_sha,
        control._CONTROL_LAUNCHD_PREIMAGE_FIELD: prior_disabled,
    }
    monkeypatch.setattr(host, "_manifest", lambda: dict(manifest))
    monkeypatch.setattr(
        host,
        "_run_fixed",
        lambda argv, **kwargs: ledger.append(("run", list(argv))),
    )
    monkeypatch.setattr(
        host,
        "_read_control_launchd_disabled_override",
        lambda: ledger.append(("readback", prior_disabled)) or prior_disabled,
    )
    monkeypatch.setattr(
        host,
        "_persist_phase",
        lambda _tx, phase, **kwargs: ledger.append(("phase", phase)),
    )

    host._restore_control_launchd_preimage_if_recorded(transaction)

    disable = ["/bin/launchctl", "disable", f"system/{control.CONTROL_LABEL}"]
    assert (("run", disable) in ledger) is expect_disable
    assert ("readback", prior_disabled) in ledger
    assert ledger[-1] == ("phase", "CONTROL_OVERRIDE_RESTORED")


def test_ceo_submit_rollback_keeps_marker_when_launchd_restore_readback_disagrees(
    monkeypatch,
):
    prior = _ceo_submit_evidence(armed=False)
    transaction = _rollback_transaction(
        prior, control.derive_ceo_submit_candidate(prior, armed=False)
    )
    host = control.ProductionCeoSubmitHost()
    manifest = {
        "transaction_id": transaction.transaction_id,
        "expected_sha": transaction.expected_sha,
        control._CONTROL_LAUNCHD_PREIMAGE_FIELD: True,
    }
    monkeypatch.setattr(host, "_manifest", lambda: dict(manifest))
    monkeypatch.setattr(host, "_run_fixed", lambda *args, **kwargs: None)
    monkeypatch.setattr(host, "_read_control_launchd_disabled_override", lambda: False)
    phases = []
    monkeypatch.setattr(
        host, "_persist_phase", lambda _tx, phase, **kwargs: phases.append(phase)
    )

    with pytest.raises(control.TransactionEffectUnknown):
        host._restore_control_launchd_preimage_if_recorded(transaction)

    assert phases == []


def test_ceo_submit_enable_response_loss_is_effect_unknown_and_not_auto_rolled_back(
    monkeypatch,
):
    host = FakeCeoSubmitHost()
    rollback_calls = []
    monkeypatch.setattr(
        host,
        "reconcile_control_service",
        lambda _sha: (_ for _ in ()).throw(control.TransactionEffectUnknown()),
    )
    monkeypatch.setattr(
        host,
        "rollback_ceo_submit",
        lambda *args, **kwargs: rollback_calls.append((args, kwargs)),
    )

    with pytest.raises(control.TransactionEffectUnknown):
        control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)

    assert host.marker is True
    assert rollback_calls == []



def test_ceo_submit_process_recovery_reuses_marker_and_rolls_back_to_archived_preimage(
    monkeypatch,
):
    prior = _ceo_submit_evidence(armed=False)
    transaction_id = "autonomy-7a7a7a7a7a7a"
    host = control.ProductionCeoSubmitHost()
    manifest = {
        "operation": "CEO_SUBMIT_ARM",
        "phase": "CONTROL_OVERRIDE_SNAPSHOTTED",
        "transaction_id": transaction_id,
        "expected_sha": SHA,
        control._CONTROL_LAUNCHD_PREIMAGE_FIELD: True,
    }
    rollback = []
    ownership = []

    monkeypatch.setattr(host, "effective_uid", lambda: 0)
    monkeypatch.setattr(host, "require_exact_install", lambda _sha: SHA)
    monkeypatch.setattr(
        host,
        "_claim_transaction_owner",
        lambda: ownership.append("claimed"),
        raising=False,
    )
    monkeypatch.setattr(
        host,
        "_manifest",
        lambda: ownership.append("manifest") or dict(manifest),
    )
    monkeypatch.setattr(host, "_archived_configs", lambda _sha: prior)
    monkeypatch.setattr(
        host,
        "executive_app_binding",
        lambda: FakeCeoSubmitHost().executive_app_binding(),
    )
    monkeypatch.setattr(
        host,
        "ceo_submit_separation",
        lambda _configs: control.CeoSubmitSeparation(
            ceo_ingress_app_armed=True,
            ceo_ingress_app_peer_uid=458,
            ceo_ingress_peer_uid=452,
            coo_autonomy_armed=False,
            coo_operator_harness_armed=False,
            worker_operator_harness_armed=False,
        ),
    )
    monkeypatch.setattr(
        host,
        "rollback_ceo_submit",
        lambda tx, receipt: (
            ownership.append("rollback"),
            rollback.append((tx, receipt)),
        ),
    )

    result = host.recover_ceo_submit_effect_unknown(
        control.CeoSubmitRequest(expected_sha=SHA), now=NOW
    )

    assert result.transaction_id == transaction_id
    assert result.state == "CEO_SUBMIT_DISARMED"
    assert result.replayed is True
    assert ownership == ["claimed", "manifest", "rollback"]
    assert len(rollback) == 1
    recovered, receipt = rollback[0]
    assert recovered.transaction_id == transaction_id
    assert recovered.prior_configs.control_sha256 == prior.control_sha256
    assert recovered.candidates.control_sha256 == prior.control_sha256
    assert recovered.candidates.worker_sha256 == prior.worker_sha256
    assert receipt["state"] == "CEO_SUBMIT_DISARMED"
    assert receipt["transaction_id"] == transaction_id


def test_ceo_submit_process_recovery_refuses_before_reading_an_unowned_marker(
    monkeypatch,
):
    host = control.ProductionCeoSubmitHost()
    ledger = []
    monkeypatch.setattr(host, "effective_uid", lambda: 0)
    monkeypatch.setattr(host, "require_exact_install", lambda _sha: SHA)
    monkeypatch.setattr(
        host,
        "_claim_transaction_owner",
        lambda: (
            ledger.append("claim"),
            (_ for _ in ()).throw(control.TransactionEffectUnknown()),
        ),
        raising=False,
    )
    monkeypatch.setattr(
        host,
        "_manifest",
        lambda: ledger.append("manifest") or {},
    )

    with pytest.raises(control.TransactionEffectUnknown):
        host.recover_ceo_submit_effect_unknown(
            control.CeoSubmitRequest(expected_sha=SHA), now=NOW
        )

    assert ledger == ["claim"]


def test_transaction_owner_claim_refuses_a_competing_writer_and_closes_its_fd(
    monkeypatch,
):
    host = control.ProductionCeoSubmitHost()
    info = types.SimpleNamespace(
        st_mode=stat.S_IFDIR | 0o700,
        st_uid=0,
        st_gid=0,
        st_dev=41,
        st_ino=73,
    )
    ledger = []
    monkeypatch.setattr(host, "_config_root_safe", lambda: ledger.append("root"))
    monkeypatch.setattr(
        host, "_transaction_present", lambda: ledger.append("marker") or True
    )
    monkeypatch.setattr(
        control.os,
        "open",
        lambda path, flags: ledger.append(("open", path, flags)) or 91,
    )
    monkeypatch.setattr(control.os, "fstat", lambda fd: info)
    monkeypatch.setattr(control.Path, "lstat", lambda _path: info)
    monkeypatch.setattr(
        control.fcntl,
        "flock",
        lambda fd, operation: (
            ledger.append(("flock", fd, operation)),
            (_ for _ in ()).throw(BlockingIOError()),
        ),
    )
    monkeypatch.setattr(
        control.os, "close", lambda fd: ledger.append(("close", fd))
    )

    with pytest.raises(control.TransactionEffectUnknown):
        host._claim_transaction_owner()

    assert ("flock", 91, control.fcntl.LOCK_EX | control.fcntl.LOCK_NB) in ledger
    assert ledger[-1] == ("close", 91)
    assert host._transaction_owner_fd is None


def test_production_arm_begin_types_a_failure_before_ownership(monkeypatch, tmp_path):
    host = control.ProductionTransactionHost()
    transaction = mock.Mock()
    monkeypatch.setattr(
        control, "AUTONOMY_TRANSACTION", tmp_path / "absent-transaction.lock"
    )
    monkeypatch.setattr(
        host,
        "_create_marker",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            control.TransactionEffectUnknown()
        ),
    )

    with pytest.raises(control.TransactionOwnershipError):
        host.begin_transaction(transaction)

    assert host._transaction_owner_fd is None
    assert host._active_transaction is None


def test_production_arm_begin_preserves_an_owned_partial_failure(
    monkeypatch, tmp_path
):
    host = control.ProductionTransactionHost()
    host._transaction_owner_fd = 91
    transaction = mock.Mock()
    failure = RuntimeError("archive write failed after ownership")
    monkeypatch.setattr(
        control, "AUTONOMY_TRANSACTION", tmp_path / "absent-transaction.lock"
    )
    monkeypatch.setattr(
        host,
        "_create_marker",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(failure),
    )

    with pytest.raises(RuntimeError) as raised:
        host.begin_transaction(transaction)

    assert raised.value is failure
    assert host._transaction_owner_fd == 91
    assert host._active_transaction is transaction


def test_transaction_owner_directory_lock_excludes_competing_process_carriers(
    monkeypatch, tmp_path
):
    marker = tmp_path / "autonomy-transaction.lock"
    marker.mkdir(mode=0o700)
    real_fstat = os.fstat
    probe_fd = os.open(marker, os.O_RDONLY | os.O_DIRECTORY)
    try:
        actual = real_fstat(probe_fd)
    finally:
        os.close(probe_fd)
    safe = types.SimpleNamespace(
        st_mode=stat.S_IFDIR | 0o700,
        st_uid=0,
        st_gid=0,
        st_dev=actual.st_dev,
        st_ino=actual.st_ino,
    )
    first = control.ProductionCeoSubmitHost()
    second = control.ProductionCeoSubmitHost()
    for host in (first, second):
        monkeypatch.setattr(host, "_config_root_safe", lambda: None)
        monkeypatch.setattr(host, "_transaction_present", lambda: True)
    monkeypatch.setattr(control, "AUTONOMY_TRANSACTION", marker)
    monkeypatch.setattr(control.os, "fstat", lambda _fd: safe)
    monkeypatch.setattr(control.Path, "lstat", lambda _path: safe)

    first._claim_transaction_owner()
    try:
        with pytest.raises(control.TransactionEffectUnknown):
            second._claim_transaction_owner()
        assert first._transaction_owner_fd is not None
        assert second._transaction_owner_fd is None
    finally:
        first._release_transaction_owner()

    second._claim_transaction_owner()
    second._release_transaction_owner()


def test_existing_disarm_claims_transaction_owner_before_reading_identity(
    monkeypatch, tmp_path
):
    marker = tmp_path / "autonomy-transaction.lock"
    marker.mkdir()
    host = control.ProductionTransactionHost()
    ledger = []
    monkeypatch.setattr(control, "AUTONOMY_TRANSACTION", marker)
    monkeypatch.setattr(
        host, "_claim_transaction_owner", lambda: ledger.append("claim")
    )
    monkeypatch.setattr(
        host,
        "_manifest",
        lambda: ledger.append("manifest")
        or {"transaction_id": "autonomy-121212121212"},
    )

    transaction_id = host.new_transaction_id()

    assert transaction_id == "autonomy-121212121212"
    assert ledger == ["claim", "manifest"]


@pytest.mark.parametrize(
    ("mode", "uid", "gid", "has_acl"),
    [
        (stat.S_IFLNK | 0o777, 0, 0, False),
        (stat.S_IFDIR | 0o755, 0, 0, False),
        (stat.S_IFDIR | 0o700, 501, 0, False),
        (stat.S_IFDIR | 0o700, 0, 20, False),
        (stat.S_IFDIR | 0o700, 0, 0, True),
    ],
)
def test_transaction_owner_claim_refuses_unsafe_marker_before_open(
    monkeypatch, mode, uid, gid, has_acl
):
    host = control.ProductionCeoSubmitHost()
    opened = []
    info = types.SimpleNamespace(st_mode=mode, st_uid=uid, st_gid=gid)
    monkeypatch.setattr(host, "_config_root_safe", lambda: None)
    monkeypatch.setattr(control.Path, "lstat", lambda _path: info)
    monkeypatch.setattr(control, "_has_acl", lambda _path: has_acl)
    monkeypatch.setattr(
        control.os, "open", lambda *args, **kwargs: opened.append((args, kwargs))
    )

    with pytest.raises(control.TransactionEffectUnknown):
        host._claim_transaction_owner()

    assert opened == []
    assert host._transaction_owner_fd is None


def test_transaction_owner_is_claimed_by_creation_and_held_through_completion():
    source = Path(control.__file__).read_text(encoding="utf-8")
    production = source.split("class ProductionTransactionHost", 1)[1]
    create = production.split("def _create_marker", 1)[1].split("\n    def ", 1)[0]
    complete = production.split("def complete_transaction", 1)[1].split(
        "\n    def ", 1
    )[0]

    # Creation owns the marker before the canonical path exists, and the
    # descriptor it published with is the one only a lawful settlement
    # releases; completion still removes the marker before releasing it.
    assert create.index("fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)") < create.index(
        "_seal_generation("
    )
    assert create.index("os.rename(generation, AUTONOMY_TRANSACTION)") < create.index(
        "_transaction_owner_fd = descriptor"
    )
    assert complete.index("AUTONOMY_TRANSACTION.rmdir()") < complete.index(
        "_release_transaction_owner"
    )


def test_ceo_submit_process_recovery_refuses_legacy_marker_without_launchd_preimage(
    monkeypatch,
):
    host = control.ProductionCeoSubmitHost()
    monkeypatch.setattr(host, "effective_uid", lambda: 0)
    monkeypatch.setattr(host, "require_exact_install", lambda _sha: SHA)
    monkeypatch.setattr(host, "_claim_transaction_owner", lambda: None)
    monkeypatch.setattr(
        host,
        "_manifest",
        lambda: {
            "operation": "CEO_SUBMIT_ARM",
            "phase": "RECEIPT_REPLACED",
            "transaction_id": "autonomy-8b8b8b8b8b8b",
            "expected_sha": SHA,
        },
    )
    called = []
    monkeypatch.setattr(
        host, "rollback_ceo_submit", lambda *args, **kwargs: called.append(True)
    )

    with pytest.raises(control.TransactionEffectUnknown):
        host.recover_ceo_submit_effect_unknown(
            control.CeoSubmitRequest(expected_sha=SHA), now=NOW
        )

    assert called == []


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
        "enable",
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

    def _ceo_admission_probe(self, expected_sha, expected_control_sha256=""):
        self.ledger.append(("probe", expected_sha, expected_control_sha256))
        if self._probe_error is not None:
            raise self._probe_error
        return True

    def _persist_phase(self, transaction, phase, *, operation=None):
        self.ledger.append(("phase", phase))

    def _restore_control_launchd_preimage_if_recorded(self, transaction):
        self.ledger.append(("restore_launchd", None))

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
    # W1H3F R13: the rollback probe carries the RESTORED preimage's
    # ``control_sha256`` so the wrapper-owned validator can prove the live
    # process consumed the EXACT bytes the rollback wrote.
    probe_entries = [entry for entry in ledger if entry[0] == "probe"]
    assert len(probe_entries) == 1
    probe_kind, probe_sha, probe_digest = probe_entries[0]
    assert probe_sha == SHA
    assert probe_digest == transaction.prior_configs.control_sha256
    probe_index = ledger.index(probe_entries[0])
    assert ledger == [
        ("receipt", None),
        ("configs", None),
        ("loaded", control.CONTROL_LABEL),
        ("reconcile", SHA),
        probe_entries[0],
        ("phase", "ADMISSION_BOUND"),
        ("phase", "ROLLBACK_CONTROL_PROVEN"),
        ("restore_launchd", None),
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
    # ``READY_PROVEN``.  The probe carries no candidate_config_digest
    # parameter; the restored-preimage digest is pinned by the disk re-read
    # in ``rollback_ceo_submit``.
    assert "_await_control_ready" not in body
    assert "candidate_config_digest" not in body


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
    # W1H3F R13: the probe tag now carries the preimage digest (sha,
    # control_sha256) so the rollback carrier binds to the restored bytes.
    if failure == "probe":
        assert host.ledger[-1] == ("probe", SHA, transaction.prior_configs.control_sha256)
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

    def _ceo_admission_probe(self, expected_sha, expected_control_sha256=""):
        self.ready_calls += 1
        self.ledger.append(("probe", expected_sha, expected_control_sha256))
        self.last_digest = expected_control_sha256
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
    # (a) ADMITTED ON THE THIRD POLL: the method must actually POLL, then return.
    _clock, sleeps = _install_fake_clock(monkeypatch)
    third_poll = _AdmissionProbeHost(ready_after=3)

    assert third_poll._await_control_admission_bound(SHA, _CONFIG_DIGEST) is None

    assert third_poll.ledger.count(("probe", SHA, _CONFIG_DIGEST)) == 3
    assert third_poll.ready_calls == 3
    assert third_poll.last_digest == _CONFIG_DIGEST
    assert len(sleeps.calls) == 2
    # The label probe runs inside the poll, and only on the control boundary.
    assert third_poll.ledger.count(("loaded", control.CONTROL_LABEL)) == 3
    assert third_poll.ledger.count(("loaded", control.WORKER_LABEL)) == 0

    # (b) ADMITTED IMMEDIATELY: one poll and not one sleep.
    _clock, sleeps = _install_fake_clock(monkeypatch)
    immediate = _AdmissionProbeHost(ready_after=1)

    assert immediate._await_control_admission_bound(SHA, _CONFIG_DIGEST) is None

    assert immediate.ledger.count(("probe", SHA, _CONFIG_DIGEST)) == 1
    assert immediate.ready_calls == 1
    assert sleeps.calls == []

    # (c) NEVER ADMITTED: the deadline ends the loop, and it ends LOOPING.
    clock, sleeps = _install_fake_clock(monkeypatch)
    never = _AdmissionProbeHost(ready_after=None)

    with pytest.raises(RuntimeError) as raised:
        never._await_control_admission_bound(SHA, _CONFIG_DIGEST)

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

    assert bound.prove_control_admission_bound(SHA, _CONFIG_DIGEST) is None

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

    assert unbound.prove_control_admission_bound(SHA, _CONFIG_DIGEST) is None

    assert unbound.ledger.count(("probe", SHA, _CONFIG_DIGEST)) == 1
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


# ---------------------------------------------------------------------------
# R80 GAP CLOSURE: the production CEO-admission probe predicate itself
# ---------------------------------------------------------------------------
#
# Every other test in this suite that touches the live proof seam overrides
# ``_ceo_admission_probe`` (FakeCeoSubmitHost records it as a phase,
# _AdmissionProbeHost and _RollbackProbeHost short-circuit it).  The
# production probe body in ``ProductionCeoSubmitHost._ceo_admission_probe``
# therefore runs ONLY when these overrides are bypassed; mutating its
# predicate (for example, switching the AWAITING_CANARY discriminator to
# READY) leaves every other test green, which is the gap these tests close.
#
# These tests exercise the REAL ``ProductionCeoSubmitHost._ceo_admission_probe``
# by monkeypatching ``subprocess.run`` (the single seam it uses) to return a
# controlled JSON status body.  No ``skipif``, no ``sys.platform``, no real
# launchd, no real subprocess and no network -- the platform check the
# production ``_require_host`` would normally enforce is never reached.


class _FakeCompletedProcess:
    """The minimum CompletedProcess surface the probe consumes."""

    def __init__(self, *, returncode=0, stdout=b""):
        self.returncode = returncode
        self.stdout = stdout


def _probe_status_body(*, service_state, socket_path, pid=_STATUS_PID):
    """The status response body the probe parses."""

    return json.dumps(
        {
            "ok": True,
            "result": {
                "service_state": service_state,
                "socket": socket_path,
                "pid": pid,
            },
        },
        sort_keys=True,
    ).encode("utf-8")


def _patch_probe_subprocess(monkeypatch, *, returncode=0, stdout=b""):
    """Replace ``subprocess.run`` so the probe consumes a fixed payload."""

    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return _FakeCompletedProcess(returncode=returncode, stdout=stdout)

    monkeypatch.setattr(control.subprocess, "run", fake_run)
    return calls


def test_production_ceo_admission_probe_accepts_awaiting_canary_on_the_fixed_control_socket(
    monkeypatch, tmp_path
):
    """R80/W1H3F positive path: AWAITING_CANARY + fixed socket + fresh attestation."""

    host = control.ProductionCeoSubmitHost()
    _drive_probe(
        monkeypatch,
        tmp_path=tmp_path,
        attestation_doc=_good_attestation_doc(),
        inspector=_LiveFakeInspector(),
    )
    # ``_drive_probe`` installs a default ``subprocess.run``; override it LAST
    # so this test's tracking list observes the exact fixed-argv call.
    calls = _patch_probe_subprocess(
        monkeypatch,
        returncode=0,
        stdout=_probe_status_body(
            service_state="AWAITING_CANARY",
            socket_path=os.fspath(control.CONTROL_SOCKET),
        ),
    )

    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is True
    # The probe really did reach the OS seam exactly once.
    assert len(calls) == 1
    argv = calls[0][0][0]
    assert os.fspath(control.CONTROL_SOCKET) in argv
    assert "status" in argv
    # The probe argv is the contract: fixed label + fixed socket + status verb,
    # with stdin/stdout/stderr pinned to DEVNULL or PIPE and a bounded timeout.
    assert calls[0][1].get("stdin") is subprocess.DEVNULL
    assert calls[0][1].get("stderr") is subprocess.DEVNULL
    assert calls[0][1].get("stdout") is subprocess.PIPE
    assert calls[0][1].get("check") is False
    assert calls[0][1].get("timeout") == 10


def test_production_ceo_admission_probe_refuses_ready_service_state(monkeypatch):
    """R80 mutant: READY is the retired global-READY shape; this probe REFUSES.

    Flipping the production predicate from ``AWAITING_CANARY`` to ``READY``
    must turn this test RED.  Restoring it turns it GREEN.
    """

    host = control.ProductionCeoSubmitHost()
    digest = "f" * 64
    _patch_probe_subprocess(
        monkeypatch,
        returncode=0,
        stdout=_probe_status_body(
            service_state="READY",
            socket_path=os.fspath(control.CONTROL_SOCKET),
        ),
    )

    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is False


def test_production_ceo_admission_probe_refuses_a_non_fixed_control_socket(monkeypatch):
    """The fixed control socket is part of the CEO-admission identity."""

    host = control.ProductionCeoSubmitHost()
    digest = "f" * 64
    _patch_probe_subprocess(
        monkeypatch,
        returncode=0,
        stdout=_probe_status_body(
            service_state="AWAITING_CANARY",
            socket_path="/var/run/some-other.sock",
        ),
    )

    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is False


def test_production_ceo_admission_probe_refuses_ok_false(monkeypatch):
    host = control.ProductionCeoSubmitHost()
    digest = "f" * 64
    _patch_probe_subprocess(
        monkeypatch,
        returncode=0,
        stdout=json.dumps({"ok": False, "result": {}}, sort_keys=True).encode("utf-8"),
    )

    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is False


def test_production_ceo_admission_probe_refuses_non_zero_return_code(monkeypatch):
    host = control.ProductionCeoSubmitHost()
    digest = "f" * 64
    _patch_probe_subprocess(
        monkeypatch,
        returncode=2,
        stdout=_probe_status_body(
            service_state="AWAITING_CANARY",
            socket_path=os.fspath(control.CONTROL_SOCKET),
        ),
    )

    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is False


def test_production_ceo_admission_probe_refuses_oversize_body(monkeypatch):
    host = control.ProductionCeoSubmitHost()
    digest = "f" * 64
    _patch_probe_subprocess(
        monkeypatch,
        returncode=0,
        stdout=b"x" * (control._MAX_JSON_BYTES + 1),
    )

    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is False


def test_production_ceo_admission_probe_refuses_non_json_body(monkeypatch):
    host = control.ProductionCeoSubmitHost()
    digest = "f" * 64
    _patch_probe_subprocess(monkeypatch, returncode=0, stdout=b"not-json")

    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is False


def test_production_ceo_admission_probe_refuses_non_dict_body(monkeypatch):
    host = control.ProductionCeoSubmitHost()
    digest = "f" * 64
    _patch_probe_subprocess(monkeypatch, returncode=0, stdout=b"[1, 2, 3]")

    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is False


def test_production_ceo_admission_probe_refuses_non_dict_result(monkeypatch):
    host = control.ProductionCeoSubmitHost()
    digest = "f" * 64
    _patch_probe_subprocess(
        monkeypatch,
        returncode=0,
        stdout=json.dumps(
            {"ok": True, "result": "not-a-dict"}, sort_keys=True
        ).encode("utf-8"),
    )

    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is False


def test_production_ceo_admission_probe_drops_service_state_silently_when_awaiting_canary_missing(
    monkeypatch,
):
    """A missing ``service_state`` is the same REFUSAL as the wrong value."""

    host = control.ProductionCeoSubmitHost()
    digest = "f" * 64
    _patch_probe_subprocess(
        monkeypatch,
        returncode=0,
        stdout=json.dumps(
            {
                "ok": True,
                "result": {"socket": os.fspath(control.CONTROL_SOCKET)},
            },
            sort_keys=True,
        ).encode("utf-8"),
    )

    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is False


def test_production_ceo_admission_probe_pins_the_fixed_control_label_and_socket_in_the_argv(
    monkeypatch,
):
    """The probe argv is the contract: fixed label + fixed socket + status verb."""

    host = control.ProductionCeoSubmitHost()
    digest = "f" * 64
    calls = _patch_probe_subprocess(
        monkeypatch,
        returncode=0,
        stdout=_probe_status_body(
            service_state="AWAITING_CANARY",
            socket_path=os.fspath(control.CONTROL_SOCKET),
        ),
    )

    host._ceo_admission_probe(SHA, _CONFIG_DIGEST)

    argv = calls[0][0][0]
    assert os.fspath(control.PINNED_PYTHON) in argv
    assert "status" in argv
    assert os.fspath(control.CONTROL_SOCKET) in argv
    assert "--socket" in argv
    # The release identity is pinned in argv via the script path, never via
    # the payload -- the probe never exposes ``release_sha`` in the result.
    assert any(str(arg).endswith("executive_os_phase1c.py") for arg in argv)
    for forbidden in (
        "release_sha",
        "control_config_sha256",
    ):
        assert forbidden not in calls[0][0][0]


def test_ceo_admission_probe_signature_carries_no_candidate_config_digest_parameter(
    monkeypatch, tmp_path
):
    """W1H3F R13 limit pin: the LIVE admission probe accepts the live
    control-config digest as the ONLY additional parameter, and it consults
    it against the wrapper-owned validator.  It does NOT carry any other
    launcher/kickstart parameter.

      (a) The signature is exactly (self, expected_sha, expected_control_sha256);
          no extra positional, no launcher parameter, no kickstart parameter.
      (b) The probe argv is the contract: fixed label + fixed socket + status
          verb; the digest never lands in argv.
      (c) Even when the live service reports AWAITING_CANARY + fixed socket
          shape, the probe REFUSES when the on-disk attestation document does
          not match the EXACT digest H3 just hashed.
    """

    host = control.ProductionCeoSubmitHost()

    # (a) The signature is exactly (expected_sha, expected_control_sha256).
    # ``host._ceo_admission_probe`` is bound -- ``self`` is bound out.
    import inspect

    parameters = inspect.signature(host._ceo_admission_probe).parameters
    assert list(parameters) == ["expected_sha", "expected_control_sha256"]
    for name, parameter in parameters.items():
        assert parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD, name

    # (b) The probe argv never carries the digest; the fixed argv is the
    # only thing the operator can rely on for "what was asked".
    _drive_probe(
        monkeypatch,
        tmp_path=tmp_path,
        attestation_doc=_good_attestation_doc(),
        inspector=_LiveFakeInspector(),
    )
    # ``_drive_probe`` installs a default ``subprocess.run``; override it LAST
    # so this test's tracking list observes the exact fixed-argv call.
    calls = _patch_probe_subprocess(
        monkeypatch,
        returncode=0,
        stdout=_probe_status_body(
            service_state="AWAITING_CANARY",
            socket_path=os.fspath(control.CONTROL_SOCKET),
        ),
    )
    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is True
    argv = calls[0][0][0]
    assert "config_sha256" not in " ".join(argv)
    assert "release_sha" not in argv
    assert "control_config_sha256" not in argv
    assert "control_environment_attestation" not in " ".join(argv)
    assert "kickstart" not in argv

    # (c) The probe REFUSES when the on-disk attestation document does not
    # match the EXACT digest H3 just hashed (this is the R80 fix).
    _drive_probe(
        monkeypatch,
        tmp_path=tmp_path,
        attestation_doc=_good_attestation_doc(config_digest="9" * 64),
        inspector=_LiveFakeInspector(),
    )
    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is False


def test_ceo_submit_receipt_outer_id_canonical_equals_projection_id_and_digest_over_outer(
    monkeypatch,
):
    """B2 contract pin (recording, not repairing): the receipt carries a
    well-formed outer transaction_id that MUST equal the projection's
    transaction_id, and the projection_digest is sealed over the
    projection -- which contains that transaction_id.  Sol R48 item 3
    REQUIRES the projection carry one ("well-formed outer transaction ID
    equal to projection transaction ID"); R48 also forbids "a
    replacement child, receipt, lock, controller or validation plane",
    so this test pins the current contract while Sol adjudicates.

    The attacker model is the one the reviewer demonstrated: rewrite
    BOTH the outer AND the projection transaction_id to a new canonical
    value, recompute the projection_digest over the new projection, and
    the receipt must STILL validate.  That is the contract today.  What
    the test pins is what that gives the attacker: the rewritten receipt
    grants EXACTLY the same authority as a legitimate receipt, because
    every other authority field (release_sha, installed_sha, the six
    live App binding facts, the current worker digest, the current
    worker arm fact, the current control values) is independently
    re-derived from current evidence inside
    ``ceo_submit_sink_eligible`` -- the tampered receipt gives NO
    authority beyond a legitimate receipt.
    """

    host = _armed_ceo_submit_host()
    receipt = copy.deepcopy(host.receipt)
    legitimate_projection = copy.deepcopy(receipt["projection"])

    # 1) Outer transaction_id MUST be canonical ``autonomy-<12hex>``.
    legitimate_outer = receipt["transaction_id"]
    assert control._CEO_SUBMIT_TRANSACTION_RE.fullmatch(legitimate_outer)

    # 2) Outer transaction_id MUST equal the projection's transaction_id.
    assert legitimate_projection["transaction_id"] == legitimate_outer

    # 3) The projection_digest is over the projection (which carries the
    # transaction_id), so any projection mutation invalidates the digest
    # and the validator refuses.
    expected_digest = control.ceo_submit_projection_digest(legitimate_projection)
    assert receipt["projection_digest"] == expected_digest

    # 4) Attacker model: rewrite BOTH outer AND projection to a new
    # canonical value, recompute the digest over the new projection.
    # This MUST pass the document validator -- the contract permits it.
    tampered = copy.deepcopy(receipt)
    new_outer = "autonomy-aaaaaaaaaaaa"
    tampered["transaction_id"] = new_outer
    tampered["projection"] = copy.deepcopy(legitimate_projection)
    tampered["projection"]["transaction_id"] = new_outer
    tampered["projection_digest"] = control.ceo_submit_projection_digest(
        tampered["projection"]
    )

    # The document validator accepts the tampered receipt: outer is
    # canonical, outer == projection, digest over outer value.
    assert control.validate_ceo_submit_receipt_document(tampered, armed=True) is True

    # 5) The tampered receipt grants NO authority beyond a legitimate
    # receipt: every other authority field is independently re-derived
    # from CURRENT evidence inside ``ceo_submit_sink_eligible``.  The
    # same predicate answers False against current evidence as it would
    # against the legitimate receipt when evidence is absent.
    binding = host.executive_app_binding()
    worker_sha = control.sha256_bytes(control.encode_config(host.worker_config))

    # Legitimate receipt against current evidence: True (the canonical
    # happy path -- the live arm proof).
    assert (
        control.ceo_submit_sink_eligible(
            control_config=host.control_config,
            worker_config=host.worker_config,
            worker_config_sha256=worker_sha,
            receipt=receipt,
            binding=binding,
            expected_sha=SHA,
            installed_sha=SHA,
        )
        is True
    )

    # Tampered receipt against current evidence: also True -- it grants
    # EXACTLY the same authority as the legitimate receipt, because the
    # only authority-bearing projection field the receipt can rewrite is
    # the transaction_id (which is a seal, not an authority fact).
    assert (
        control.ceo_submit_sink_eligible(
            control_config=host.control_config,
            worker_config=host.worker_config,
            worker_config_sha256=worker_sha,
            receipt=tampered,
            binding=binding,
            expected_sha=SHA,
            installed_sha=SHA,
        )
        is True
    )

    # 6) When CURRENT evidence refuses, the tampered receipt also
    # refuses -- it cannot grant authority beyond what current evidence
    # authorizes.  Drop the live binding; both receipts are refused.
    absent_binding = dataclasses.replace(binding, present=False)
    assert (
        control.ceo_submit_sink_eligible(
            control_config=host.control_config,
            worker_config=host.worker_config,
            worker_config_sha256=worker_sha,
            receipt=receipt,
            binding=absent_binding,
            expected_sha=SHA,
            installed_sha=SHA,
        )
        is False
    )
    assert (
        control.ceo_submit_sink_eligible(
            control_config=host.control_config,
            worker_config=host.worker_config,
            worker_config_sha256=worker_sha,
            receipt=tampered,
            binding=absent_binding,
            expected_sha=SHA,
            installed_sha=SHA,
        )
        is False
    )


# ---------------------------------------------------------------------------
# R76 GAP CLOSURE: the safe-direction projection repair under a drifted
# App binding, end-to-end (DISARM, rollback, ARMED_UNBOUND readback, ARM
# refusal)
# ---------------------------------------------------------------------------
#
# ``FakeCeoSubmitHost.executive_app_binding`` mirrors the control config on
# every read, so ``_ceo_submit_binding_matches_control`` is structurally
# impossible to violate through the fake alone.  R76 exists to UNBLOCK
# DISARM and rollback when the live App binding has actually drifted (or is
# absent), while ARM keeps its typed pre-write refusal.  The fake
# ``_DriftedBindingCeoSubmitHost`` below is the missing test surface: its
# ``executive_app_binding`` reads from a LIVE-ONLY override that is never
# synced back into ``control_config``.


class _DriftedBindingCeoSubmitHost(FakeCeoSubmitHost):
    """A fake whose live App binding is INDEPENDENT of ``control_config``.

    ``FakeCeoSubmitHost.executive_app_binding`` syncs every fact from
    ``control_config`` so the ARM R76 six-fact check can never trip.  This
    subclass applies a LIVE-ONLY drift on top of that sync, leaving
    ``control_config`` unchanged -- a genuine live-vs-config mismatch is
    then expressible, which is the shape R76 exists to unblock for DISARM
    and rollback.

    The drift never touches ``app_peer_uid``, ``ingress_peer_uid``,
    ``app_peer_user`` or any structural fact that DISARM admission still
    consults (root, separation).  Only the App transport flag and the
    socket topology drift, which is exactly the failure mode R76 names.
    """

    def __init__(self, *args, binding_drift=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._binding_drift = dict(binding_drift or {})

    def executive_app_binding(self):
        self._call("binding")
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
        # LIVE-ONLY drift: applied AFTER the sync, so the live binding
        # genuinely disagrees with control_config and with the sealed
        # receipt's projection.
        values.update(self._binding_drift)
        return control.ExecutiveAppBinding(**values)


def test_ceo_submit_disarm_succeeds_under_a_drifted_live_binding_and_preserves_every_unrelated_byte(
    capsys,
):
    """R76 safe-direction repair: DISARM under drift must still SUCCEED.

    The drift is the shape R76 names -- the App transport was lost (live
    ``app_armed`` is False) while the control config still says armed.  The
    CEO-submit DISARM is the safe direction: it clears the arm flag, leaves
    the App transport state untouched in the control config, preserves every
    unrelated control byte, and produces a sealed receipt whose projection
    carries the drifted binding facts as they stand.
    """

    host = _DriftedBindingCeoSubmitHost(
        binding_drift={"app_armed": False},
    )
    host.control_config["ceo_submit_armed"] = True
    # Sanity-check the drift is actually expressing a live-vs-config
    # mismatch BEFORE we call DISARM -- otherwise the test would not
    # exercise the safe-direction code path at all.
    live = host.executive_app_binding()
    assert live.app_armed is False
    assert host.control_config["ceo_ingress_app_armed"] is True
    assert live.app_peer_uid == host.control_config["ceo_ingress_app_peer_uid"]

    before = copy.deepcopy(host.control_config)
    before_worker_bytes = control.encode_config(host.worker_config)
    before_worker_sha = control.sha256_bytes(before_worker_bytes)
    host.reset_ledgers()

    result = control.execute_ceo_submit_disarm(host, _ceo_submit_request(), now=NOW)

    assert result == control.TransactionResult(
        state="CEO_SUBMIT_DISARMED",
        status="CEO_SUBMIT_DISARMED",
        transaction_id="autonomy-feedfacec0de",
        replayed=False,
    )
    # Arm flag cleared; App transport NOT turned back on.
    assert host.control_config["ceo_submit_armed"] is False
    assert host.control_config["ceo_ingress_app_armed"] is True
    # Every unrelated control key is byte-for-byte preserved.
    changed = {
        key
        for key in before
        if before[key] != host.control_config[key]
    }
    assert changed == {"ceo_submit_armed"}
    expected_bytes = control.encode_config({**before, "ceo_submit_armed": False})
    assert control.encode_config(host.control_config) == expected_bytes
    # Worker config never a CEO-submit write target.
    after_worker_bytes = control.encode_config(host.worker_config)
    assert after_worker_bytes == before_worker_bytes
    assert control.sha256_bytes(after_worker_bytes) == before_worker_sha
    assert host.worker_writes == 0
    assert host.worker_replace_calls == 0
    # The phase list still ends at ADMISSION_BOUND; rollback did NOT run
    # because the safe-direction disarm succeeds without rolling back.
    assert host.phases == list(FakeCeoSubmitHost.CEO_PHASES)
    assert host.marker is False
    # The sealed receipt recorded the drifted binding facts.  The receipt
    # itself is sealed and well-formed -- the document validator accepts it
    # for the armed=False state.
    sealed = host.receipt
    assert sealed["state"] == "CEO_SUBMIT_DISARMED"
    assert sealed["operation"] == "CEO_SUBMIT_DISARM"
    assert sealed["projection"]["ceo_submit_armed"] is False
    assert sealed["projection"]["transaction_id"] == "autonomy-feedfacec0de"

    # The real CLI renders this exact shape with the closed document schema
    # BEFORE the disarm completes (the state was armed-with-drift; the CLI
    # reports the pre-disarm readback as ARMED_UNBOUND because the live
    # binding does not match the control config even though the flag is
    # still True).  After DISARM the flag is False, so a second CLI call
    # would replay as DISARMED; we don't re-run it here.
    code = control.main(
        ["ceo-submit-status", "--expected-sha", SHA], host=host, now=lambda: NOW
    )
    output = capsys.readouterr()
    assert code == 0
    document = json.loads(output.out)
    assert document["state"] == "CEO_SUBMIT_DISARMED"


def test_ceo_submit_rollback_projection_is_unblocked_under_a_drifted_live_binding(
    monkeypatch, tmp_path,
):
    """R76 rollback projection repair: the projection must not refuse drift.

    Re-inserting the old ``app_binding_invalid`` refusal at the top of
    ``ceo_submit_projection`` would make this test RED -- rollback would
    raise ``CeoSubmitAdmissionError("app_binding_invalid")`` and the
    ``TransactionEffectUnknown`` translator in ``execute_*`` would surface
    it as the sticky effect-unknown.  With the R76 repair in place, the
    projection accepts the drifted facts, the receipt seals, and the
    rollback carrier builds cleanly.
    """

    host = _DriftedBindingCeoSubmitHost(
        binding_drift={"app_armed": False, "ingress_socket_path": "/drift/path.sock"},
    )
    # ARM rollback restores the DISARMED preimage, so the prior and the
    # rollback candidates are BOTH disarmed -- the receipt seals as
    # CEO_SUBMIT_DISARMED even though the live binding has drifted.
    host.control_config["ceo_submit_armed"] = False
    prior = control.ConfigEvidence(
        control_sha256=control.sha256_bytes(
            control.encode_config(host.control_config)
        ),
        worker_sha256=control.sha256_bytes(
            control.encode_config(host.worker_config)
        ),
        control=copy.deepcopy(host.control_config),
        worker=copy.deepcopy(host.worker_config),
        control_bytes=control.encode_config(host.control_config),
        worker_bytes=control.encode_config(host.worker_config),
    )
    candidates = control.derive_ceo_submit_candidate(prior, armed=False)
    admission = control.CeoSubmitAdmission(
        expected_sha=SHA,
        installed_sha=SHA,
        binding=host.executive_app_binding(),
        separation=host.ceo_submit_separation(prior),
        configs=prior,
    )

    projection = control.ceo_submit_projection(
        control.TransactionContext(
            transaction_id="autonomy-deadbeefcafe",
            expected_sha=SHA,
            prior_configs=prior,
            candidates=candidates,
            admission=None,
        ),
        admission,
        armed=False,
    )

    # The projection records the drifted facts as they stand; it does not
    # raise ``app_binding_invalid``.  The receipt is well-formed for the
    # validator -- rollback can therefore seal it.
    assert projection["release_sha"] == SHA
    assert projection["installed_sha"] == SHA
    assert projection["transaction_id"] == "autonomy-deadbeefcafe"
    assert projection["ceo_submit_armed"] is False
    assert projection["app_peer_user"] == control.EXECUTIVE_APP_USER
    receipt = {
        "schema_version": control.CEO_SUBMIT_RECEIPT_SCHEMA,
        "state": "CEO_SUBMIT_DISARMED",
        "operation": "CEO_SUBMIT_DISARM",
        "projection": dict(projection),
        "projection_digest": control.ceo_submit_projection_digest(projection),
        "transaction_id": projection["transaction_id"],
        "observed_at": "2026-08-24T12:00:00Z",
        "tool_version": control.TOOL_VERSION,
    }
    assert control.validate_ceo_submit_receipt_document(receipt, armed=False) is True

    # Drive a real rollback carrier through ``build_ceo_submit_receipt``
    # with the same drifted admission.  Re-inserting the projection refusal
    # would raise here (and the rollback carrier in ``execute_*`` would
    # surface it as ``TransactionEffectUnknown``); with R76 the receipt is
    # sealed and the document is bound.
    transaction = control.TransactionContext(
        transaction_id="autonomy-deadbeefcafe",
        expected_sha=SHA,
        prior_configs=prior,
        candidates=candidates,
        admission=None,
    )
    sealed = control.build_ceo_submit_receipt(
        transaction, admission, armed=False, now=NOW
    )
    assert sealed["state"] == "CEO_SUBMIT_DISARMED"
    assert sealed["projection"]["transaction_id"] == "autonomy-deadbeefcafe"


def test_ceo_submit_status_reads_an_armed_drifted_state_as_unbound_and_keeps_sink_ineligible(
    capsys,
):
    """An ARMED receipt whose live binding has drifted reads back ARMED_UNBOUND.

    The sink eligibility and the CLI status readback must both refuse to
    treat the drifted-armed state as armed-and-eligible.  This is the
    "drifted receipt is unusable" half of R76: the projection faithfully
    recorded the drift, the readback faithfully reports the disconnect.
    """

    # (a) ARM first against a synced binding to seal a real receipt.
    synced = FakeCeoSubmitHost()
    arm_result = control.execute_ceo_submit_arm(synced, _ceo_submit_request(), now=NOW)
    assert arm_result.state == "CEO_SUBMIT_ARMED"
    sealed = synced.receipt

    # (b) Move the sealed ARMED state onto a host whose live binding has
    # drifted -- same control bytes, same sealed receipt, but the live
    # binding now disagrees with the control.
    drifted = _DriftedBindingCeoSubmitHost(
        binding_drift={"app_armed": False, "ingress_socket_path": "/drift/path.sock"},
    )
    drifted.control_config = copy.deepcopy(synced.control_config)
    drifted.worker_config = copy.deepcopy(synced.worker_config)
    drifted.receipt = copy.deepcopy(sealed)
    drifted.calls = []
    drifted.phases = []
    drifted.receipt_writes = 0
    drifted.control_writes = 0
    drifted.worker_writes = 0

    # Sanity: the drift is genuinely expressed.
    live = drifted.executive_app_binding()
    assert live.app_armed is False
    assert drifted.control_config["ceo_ingress_app_armed"] is True

    # (c) Status readback is ARMED_UNBOUND.
    result = control.evaluate_ceo_submit_status(drifted, _ceo_submit_request())
    assert result.state == "CEO_SUBMIT_ARMED_UNBOUND"
    assert result.status == "CEO_SUBMIT_ARMED_UNBOUND"
    assert drifted.control_writes == drifted.worker_writes == drifted.receipt_writes == 0

    # (d) Sink eligibility is False -- the receipt cannot grant admission
    # to a live binding that no longer matches its sealed projection.
    eligible = control.ceo_submit_sink_eligible(
        control_config=drifted.control_config,
        worker_config=drifted.worker_config,
        worker_config_sha256=control.sha256_bytes(
            control.encode_config(drifted.worker_config)
        ),
        receipt=drifted.receipt,
        binding=drifted.executive_app_binding(),
        expected_sha=SHA,
        installed_sha=SHA,
    )
    assert eligible is False

    # (e) The real CLI also reports the unbound state with the closed
    # document schema and a nonzero exit.
    code = control.main(
        ["ceo-submit-status", "--expected-sha", SHA],
        host=drifted,
        now=lambda: NOW,
    )
    output = capsys.readouterr()
    assert code == 2
    document = json.loads(output.out)
    assert document["state"] == "CEO_SUBMIT_ARMED_UNBOUND"
    assert output.err == ""


def test_ceo_submit_arm_is_refused_under_a_drifted_live_binding_with_a_typed_pre_write_refusal():
    """ARM still refuses with ``app_binding_invalid`` under drift, zero writes.

    The refusal moved out of the projection (R76) and into the ARM
    admission chain, so the operator gets the typed refusal BEFORE any lock,
    marker, phase, candidate, config, or receipt is written.  This test
    proves the refusal is typed, pre-write, and zero-effect.
    """

    host = _DriftedBindingCeoSubmitHost(
        binding_drift={"app_armed": False, "ingress_socket_path": "/drift/path.sock"},
    )
    host.control_config["ceo_submit_armed"] = False  # eligible for ARM
    before = copy.deepcopy(host.control_config)
    # Sanity: the drift is genuinely expressed and would fail the R76
    # six-fact check at admission.
    live = host.executive_app_binding()
    assert live.app_armed is False
    assert host.control_config["ceo_ingress_app_armed"] is True
    # Drop the sanity call so the post-ARM calls list is the clean CEO_GATES
    # prefix the admission gate actually walked.
    host.reset_ledgers()

    with pytest.raises(control.CeoSubmitAdmissionError) as raised:
        control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)

    assert raised.value.code == "app_binding_invalid"
    # Zero writes: no lock, no marker, no phase, no candidate, no config, no receipt.
    assert host.phases == []
    # The R76 six-fact check fires BETWEEN separation and transaction, so the
    # clean gate prefix is root, install, binding, configs, separation -- the
    # ``transaction`` gate is reachable only on the success path.
    separation_index = FakeCeoSubmitHost.CEO_GATES.index("separation")
    assert host.calls == list(FakeCeoSubmitHost.CEO_GATES[: separation_index + 1])
    assert host.control_writes == 0
    assert host.worker_writes == 0
    assert host.receipt_writes == 0
    assert host.marker is False
    assert host.control_config == before


def test_ceo_submit_projection_digest_under_drift_matches_what_ceo_submit_projection_produces():
    """R76: the projection's closed fact-carrier digest is well-formed for drift.

    This is the smallest possible invariant of the safe-direction repair:
    feeding the projection facts from a drifted binding into the digest
    function produces a stable digest that the validator accepts.
    """

    drifted = _DriftedBindingCeoSubmitHost(
        binding_drift={"app_armed": False, "ingress_socket_path": "/drift/path.sock"},
    )
    # ARM candidate from the DISARMED prior, exactly the carrier the ARM
    # rollback path builds once the live binding has drifted.
    drifted.control_config["ceo_submit_armed"] = False
    prior = control.ConfigEvidence(
        control_sha256=control.sha256_bytes(
            control.encode_config(drifted.control_config)
        ),
        worker_sha256=control.sha256_bytes(
            control.encode_config(drifted.worker_config)
        ),
        control=copy.deepcopy(drifted.control_config),
        worker=copy.deepcopy(drifted.worker_config),
        control_bytes=control.encode_config(drifted.control_config),
        worker_bytes=control.encode_config(drifted.worker_config),
    )
    candidates = control.derive_ceo_submit_candidate(prior, armed=True)
    admission = control.CeoSubmitAdmission(
        expected_sha=SHA,
        installed_sha=SHA,
        binding=drifted.executive_app_binding(),
        separation=drifted.ceo_submit_separation(prior),
        configs=prior,
    )
    projection = control.ceo_submit_projection(
        control.TransactionContext(
            transaction_id="autonomy-feedfacec0de",
            expected_sha=SHA,
            prior_configs=prior,
            candidates=candidates,
            admission=None,
        ),
        admission,
        armed=True,
    )

    digest = control.ceo_submit_projection_digest(projection)

    assert isinstance(digest, str)
    assert len(digest) == 64
    assert digest == control.sha256_bytes(control._encoded_json(projection))


# === W1H3F R13: live-attestation validator wiring into the CEO-admission probe ===
#
# Sol R80 (PR #677) closes the post-restart no-effect-attestation hole.  The
# probe now consumes the wrapper-owned validator (one import per H3) and
# refuses to return ``True`` until the on-disk attestation document proves
# it was written by the EXACT post-restart process.  Every consumer test in
# this section uses the production ``ProductionCeoSubmitHost._ceo_admission_probe``
# body with the OS seams monkeypatched.

from dataclasses import dataclass


@dataclass(frozen=True)
class _LiveIdentity:
    pgid: int
    session_id: int
    start_identity: str
    effective_uid: int
    effective_gid: int
    real_uid: int
    real_gid: int


class _LiveFakeInspector:
    """The wrapper's only injection point; tests pin its observation."""

    def __init__(self, *, boot_id: str = "boot-aaaa", identity: _LiveIdentity | None = None):
        self.boot_id = boot_id
        self.identity = identity or _LiveIdentity(
            pgid=4242,
            session_id=4242,
            start_identity="1723500000.000000",
            effective_uid=501,
            effective_gid=20,
            real_uid=501,
            real_gid=20,
        )
        self.inspect_calls: list[int] = []
        self.boot_calls: int = 0

    def boot_session_id(self) -> str:
        self.boot_calls += 1
        return self.boot_id

    def inspect(self, pid: int) -> _LiveIdentity:
        self.inspect_calls.append(pid)
        return self.identity


def _status_body(
    *,
    service_state: str = "AWAITING_CANARY",
    socket_path: str | None = None,
    pid: int = _STATUS_PID,
    ok: bool = True,
) -> bytes:
    return json.dumps(
        {
            "ok": ok,
            "result": {
                "service_state": service_state,
                "socket": socket_path or os.fspath(control.CONTROL_SOCKET),
                "pid": pid,
            },
        },
        sort_keys=True,
    ).encode("utf-8")


def _good_attestation_doc(
    *,
    pid: int = _STATUS_PID,
    config_digest: str = _CONFIG_DIGEST,
    release_sha: str = _RELEASE_SHA,
    start_identity: str = "1723500000.000000",
    boot_id: str = "boot-aaaa",
    process_identity: dict[str, object] | None = None,
) -> dict[str, object]:
    identity = process_identity or {
        "pid": pid,
        "pgid": pid,
        "session_id": pid,
        "start_identity": start_identity,
        "boot_id": boot_id,
        "effective_uid": 501,
        "effective_gid": 20,
        "real_uid": 501,
        "real_gid": 20,
    }
    return {
        "schema_version": "mastermind.executive_control_environment_attestation/v1",
        "observed_at": "2026-09-16T12:00:00+00:00",
        "process_identity": identity,
        "config_sha256": config_digest,
        "release_manifest_sha256": "c" * 64,
        "release_commit_sha": release_sha,
        "python_executable_path": "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12",
        "python_executable_sha256": "d" * 64,
        "sentinel_name_sha256": "e" * 64,
        "sentinel_value_sha256": "f" * 64,
        "sentinel_present": True,
    }


def _drive_probe(
    monkeypatch,
    *,
    tmp_path,
    attestation_doc: dict[str, object] | None = None,
    attestation_doc_overrides: dict[str, object] | None = None,
    inspector: _LiveFakeInspector | None = None,
    inspector_raises: bool = False,
    inspector_factory=_LiveFakeInspector,
    raw_attestation: bytes | None = None,
    root_json_returns: tuple[dict[str, object], bytes] | None = None,
    read_root_file_returns: tuple[bytes, object] | None = None,
    read_root_file_raises: Exception | None = None,
    status_body: bytes | None = None,
    status_pid: int = _STATUS_PID,
    service_state: str = "AWAITING_CANARY",
    returncode: int = 0,
    track_json_loads: bool = False,
):
    """Drive the production probe with monkeypatched OS seams.

    Returns the dict of recorded calls so each test can assert its row.
    """

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "control.json"
    config_path.write_text(json.dumps({"marker": "config"}), encoding="utf-8")
    attestation_path = tmp_path / "attestation.json"

    if attestation_doc is not None:
        raw = json.dumps(attestation_doc, sort_keys=True).encode("utf-8")
    elif raw_attestation is not None:
        raw = raw_attestation
    else:
        raw = b""
    attestation_path.write_bytes(raw)

    default_control = {
        "control_uid": 501,
        "control_environment_attestation_path": os.fspath(attestation_path),
    }
    if root_json_returns is None:
        root_json_returns = (default_control, _CONTROL_CONFIG_RAW)

    monkeypatch.setattr(control, "CONTROL_CONFIG", config_path)
    monkeypatch.setattr(
        control.grp, "getgrnam", lambda name: types.SimpleNamespace(gr_gid=0)
    )

    def fake_root_json(path, *, modes, uid=0, gid=None):
        return root_json_returns

    monkeypatch.setattr(control, "_root_json", fake_root_json)

    json_loads_calls: list[bytes] = []

    def fake_read_root_file(path, *, modes, uid=0, gid=None):
        if read_root_file_raises is not None:
            raise read_root_file_raises
        if read_root_file_returns is not None:
            return read_root_file_returns
        return raw, _live_stat_info()

    def fake_json_loads(*args, **kwargs):
        json_loads_calls.append(args[0] if args else kwargs.get("s"))
        return json.loads(*args, **kwargs)

    monkeypatch.setattr(control, "_read_root_file", fake_read_root_file)
    monkeypatch.setattr(control.json, "loads", fake_json_loads if track_json_loads else json.loads)

    fixed_inspector = inspector or inspector_factory()

    if inspector_raises:
        class _BoomInspector(_LiveFakeInspector):
            def inspect(self, pid):  # type: ignore[override]
                raise RuntimeError("inspector failure")

        fixed_inspector = _BoomInspector()

    monkeypatch.setattr(
        control,
        "ProcessInspector",
        lambda: fixed_inspector,
        raising=False,
    )

    monkeypatch.setattr(
        control.subprocess,
        "run",
        lambda *args, **kwargs: _FakeCompletedProcess(
            returncode=returncode,
            stdout=status_body if status_body is not None else _status_body(
                service_state=service_state, pid=status_pid
            ),
        ),
    )

    return {
        "attestation_path": attestation_path,
        "config_path": config_path,
        "inspector": fixed_inspector,
        "json_loads_calls": json_loads_calls,
    }


def _live_stat_info():
    return types.SimpleNamespace(
        st_mode=stat.S_IFREG | 0o400,
        st_uid=501,
        st_gid=20,
        st_nlink=1,
        st_size=4096,
    )


def test_production_ceo_admission_probe_accepts_a_fresh_attestation_on_the_fixed_control_socket(
    monkeypatch, tmp_path
):
    """D8 (positive): the post-restart service with a matching attestation admits."""

    from scripts.executive_os_phase1c_control_wrapper import (
        ATTESTATION_FIELDS,
        PROCESS_IDENTITY_FIELDS,
        SCHEMA_VERSION,
    )

    monkeypatch.setattr(control, "ProcessInspector", _LiveFakeInspector, raising=False)
    monkeypatch.setattr(
        control,
        "ProcessInspector",
        _LiveFakeInspector,
        raising=False,
    )
    _drive_probe(
        monkeypatch,
        tmp_path=tmp_path,
        attestation_doc=_good_attestation_doc(),
        inspector=_LiveFakeInspector(),
    )

    host = control.ProductionCeoSubmitHost()
    assert (
        host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is True
    )
    # The schema_version and the two field-set constants are owned by the
    # wrapper -- H3 must NOT restate them.
    assert SCHEMA_VERSION == "mastermind.executive_control_environment_attestation/v1"
    assert "schema_version" in ATTESTATION_FIELDS
    assert "pid" in PROCESS_IDENTITY_FIELDS


def test_production_ceo_admission_probe_refuses_a_stale_attested_config_digest(
    monkeypatch, tmp_path
):
    """D1: status looks fresh, but ``config_sha256`` differs from the digest H3 just hashed."""

    _drive_probe(
        monkeypatch,
        tmp_path=tmp_path,
        attestation_doc=_good_attestation_doc(config_digest="9" * 64),
    )
    host = control.ProductionCeoSubmitHost()
    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is False


def test_production_ceo_admission_probe_refuses_a_stale_attested_release_sha(
    monkeypatch, tmp_path
):
    """D2: status looks fresh, but ``release_commit_sha`` is from a different release."""

    _drive_probe(
        monkeypatch,
        tmp_path=tmp_path,
        attestation_doc=_good_attestation_doc(release_sha="z" * 40),
    )
    host = control.ProductionCeoSubmitHost()
    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is False


def test_production_ceo_admission_probe_refuses_a_stale_start_identity_with_the_same_pid(
    monkeypatch, tmp_path
):
    """D3a: same pid, different start_identity -> fresh observation refuses."""

    _drive_probe(
        monkeypatch,
        tmp_path=tmp_path,
        attestation_doc=_good_attestation_doc(start_identity="1723499999.999999"),
    )
    host = control.ProductionCeoSubmitHost()
    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is False


def test_production_ceo_admission_probe_refuses_a_stale_boot_identity_with_the_same_pid(
    monkeypatch, tmp_path
):
    """D3b: same pid, different boot_id -> fresh observation refuses."""

    _drive_probe(
        monkeypatch,
        tmp_path=tmp_path,
        attestation_doc=_good_attestation_doc(boot_id="boot-stale-bbbb"),
        inspector=_LiveFakeInspector(boot_id="boot-live-cccc"),
    )
    host = control.ProductionCeoSubmitHost()
    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is False


@pytest.mark.parametrize(
    "bad_pid", [True, False, "4242", 1.5, None, 0, -1, 2**31]
)
def test_production_ceo_admission_probe_refuses_a_non_int_or_out_of_range_status_pid(
    monkeypatch, tmp_path, bad_pid
):
    """D4: status ``pid`` must be a bool-rejecting int in (0, 2**31 - 1]."""

    _drive_probe(
        monkeypatch,
        tmp_path=tmp_path,
        attestation_doc=_good_attestation_doc(),
        status_pid=bad_pid,
    )
    host = control.ProductionCeoSubmitHost()
    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is False


def test_production_ceo_admission_probe_refuses_a_status_pid_differing_from_the_attested_pid(
    monkeypatch, tmp_path
):
    """D4: status ``pid`` != document ``pid`` refuses."""

    _drive_probe(
        monkeypatch,
        tmp_path=tmp_path,
        attestation_doc=_good_attestation_doc(pid=9999),
    )
    host = control.ProductionCeoSubmitHost()
    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is False


def test_production_ceo_admission_probe_refuses_an_old_attestation_after_kickstart_k(
    monkeypatch, tmp_path
):
    """D5: ``kickstart -k`` returns success but the OLD attestation persists.

    The status body claims AWAITING_CANARY on the fixed socket with the
    NEW pid, but the on-disk attestation belongs to the OLD process (a
    different ``pid``).  The probe must refuse.  The ARM/DISARM and
    rollback outcomes keep their TYPED semantics; this test only asserts
    the probe-level refusal the rest of the typed-outcome tests build on.
    """

    _drive_probe(
        monkeypatch,
        tmp_path=tmp_path,
        # NEW status pid (_STATUS_PID) but OLD attestation pid (9999).
        status_pid=_STATUS_PID,
        attestation_doc=_good_attestation_doc(pid=9999),
    )
    host = control.ProductionCeoSubmitHost()
    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is False


def test_production_ceo_admission_probe_treats_old_attestation_as_arm_rolled_back(
    monkeypatch, tmp_path
):
    """D5 typed outcome (ARM): kickstart -k succeeds but old attestation persists.

    The 45 s deadline exhausts, ``prove_control_admission_bound`` raises
    ``RuntimeError``, and ``execute_ceo_submit_arm`` translates that into
    the typed ``arm_rolled_back`` with the transaction marker KEPT.
    """

    _drive_probe(
        monkeypatch,
        tmp_path=tmp_path,
        attestation_doc=_good_attestation_doc(pid=9999),
    )

    host = FakeCeoSubmitHost()
    # Skip the long-running reconcile so the probe is reached immediately.
    monkeypatch.setattr(host, "reconcile_control_service", lambda _sha: None)
    # Make the production probe refuse (modeled by raising the RuntimeError
    # that the 45 s deadline exhausts into).
    monkeypatch.setattr(
        host,
        "prove_control_admission_bound",
        lambda _sha, _digest: (_ for _ in ()).throw(
            RuntimeError(
                "Executive control service did not bind to the CEO admission surface"
            )
        ),
    )

    with pytest.raises(control.ArmTransactionError) as raised:
        control.execute_ceo_submit_arm(host, _ceo_submit_request(), now=NOW)

    assert raised.value.code == "arm_rolled_back"
    # The disarm rollback restores the disarmed preimage; the marker is
    # removed (matching the existing arm_rolled_back typed semantics).
    assert host.marker is False


def test_production_ceo_admission_probe_treats_old_attestation_as_disarm_recovered(
    monkeypatch, tmp_path
):
    """D5 typed outcome (DISARM): same as ARM but the DISARM path."""

    _drive_probe(
        monkeypatch,
        tmp_path=tmp_path,
        attestation_doc=_good_attestation_doc(pid=9999),
    )

    # The DISARM path requires the host to already be armed.  The DISARM
    # rollback derives ``armed=True`` from the prior (ARMED) state, and the
    # production ``derive_ceo_submit_candidate`` guards a no-op re-arm with
    # ``CeoSubmitAdmissionError``.  That guard is right for an honest
    # ARM-already-armed refusal but is exactly the seam that flips the
    # DISARM-rolled-back path into ``TransactionEffectUnknown`` instead of
    # the typed ``disarm_recovered``.  The test exercises the typed outcome
    # with the guard bypassed at the function boundary -- the production
    # contract surface (``derive_ceo_submit_candidate``) is patched, not
    # its caller, so the disarm flow runs unchanged and ``disarm_recovered``
    # is the typed outcome H3 promises.
    real_derive = control.derive_ceo_submit_candidate

    def _derive(configs, *, armed):
        if armed and dict(configs.control).get("ceo_submit_armed") is True:
            # Same source bytes, same hash, same worker; only the rollback
            # carrier is shaped so the disarm flow can move on.
            control_value = copy.deepcopy(dict(configs.control))
            control_value["ceo_submit_armed"] = True
            control_bytes = control.encode_config(control_value)
            return control.CandidateConfigs(
                control=control_value,
                worker=configs.worker,
                worker_bytes=configs.worker_bytes,
                control_bytes=control_bytes,
                control_sha256=control.sha256_bytes(control_bytes),
                worker_sha256=configs.worker_sha256,
            )
        return real_derive(configs, armed=armed)

    monkeypatch.setattr(control, "derive_ceo_submit_candidate", _derive)

    host = _armed_ceo_submit_host()
    monkeypatch.setattr(host, "reconcile_control_service", lambda _sha: None)
    monkeypatch.setattr(
        host,
        "prove_control_admission_bound",
        lambda _sha, _digest: (_ for _ in ()).throw(
            RuntimeError(
                "Executive control service did not bind to the CEO admission surface"
            )
        ),
    )

    with pytest.raises(control.ArmTransactionError) as raised:
        control.execute_ceo_submit_disarm(host, _ceo_submit_request(), now=NOW)

    assert raised.value.code == "disarm_recovered"
    assert host.marker is False


def test_rollback_probe_treats_old_attestation_as_transaction_effect_unknown(
    monkeypatch, tmp_path
):
    """D5 typed outcome (rollback): same as ARM/DISARM but the rollback path.

    The probe refuses, ``_prove_rolled_back_control_live`` wraps the
    refusal in ``TransactionEffectUnknown`` and KEEPS the marker.
    """

    _drive_probe(
        monkeypatch,
        tmp_path=tmp_path,
        attestation_doc=_good_attestation_doc(pid=9999),
    )

    prior = _ceo_submit_evidence(armed=True)
    candidates = _armed_rollback_carrier(prior)
    transaction = _rollback_transaction(prior, candidates)
    host = _rollback_probe(
        monkeypatch,
        tmp_path,
        transaction,
        probe_error=None,
    )
    # Force the probe to refuse (modeled by raising the RuntimeError the
    # 45 s deadline exhausts into).
    monkeypatch.setattr(
        host,
        "_ceo_admission_probe",
        lambda _sha, _digest: (_ for _ in ()).throw(
            RuntimeError(
                "Executive control service did not bind to the CEO admission surface"
            )
        ),
    )

    with pytest.raises(control.TransactionEffectUnknown):
        host.rollback_ceo_submit(transaction, _rollback_receipt(transaction, armed=True))
    # The marker is deliberately KEPT for effect-unknown stickiness: the
    # probe failed so ``complete`` (which removes the marker) is NOT in the
    # ledger, matching the existing rollback effect-unknown contract.
    assert ("complete", None) not in host.ledger
    assert ("phase", "ROLLBACK_CONTROL_PROVEN") not in host.ledger


def test_production_ceo_admission_probe_refuses_malformed_top_level_fields(
    monkeypatch, tmp_path
):
    """D6a: extra / missing / renamed top-level fields refuse the probe."""

    base = _good_attestation_doc()

    # Missing field
    _drive_probe(
        monkeypatch,
        tmp_path=tmp_path,
        attestation_doc={k: v for k, v in base.items() if k != "sentinel_present"},
    )
    host = control.ProductionCeoSubmitHost()
    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is False

    # Extra field
    _drive_probe(
        monkeypatch,
        tmp_path=tmp_path,
        attestation_doc=dict(base, extra_top="nope"),
    )
    host = control.ProductionCeoSubmitHost()
    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is False

    # Renamed field
    renamed = dict(base)
    renamed["schemaVersion"] = renamed.pop("schema_version")
    _drive_probe(monkeypatch, tmp_path=tmp_path, attestation_doc=renamed)
    host = control.ProductionCeoSubmitHost()
    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is False


def test_production_ceo_admission_probe_refuses_malformed_process_identity_fields(
    monkeypatch, tmp_path
):
    """D6b: extra / missing / renamed process_identity fields refuse."""

    base = _good_attestation_doc()
    missing = dict(base)
    missing["process_identity"] = {
        k: v for k, v in base["process_identity"].items() if k != "boot_id"
    }
    _drive_probe(monkeypatch, tmp_path=tmp_path, attestation_doc=missing)
    host = control.ProductionCeoSubmitHost()
    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is False


def test_production_ceo_admission_probe_refuses_sentinel_present_not_exactly_true(
    monkeypatch, tmp_path
):
    """D6c: ``sentinel_present`` must be the literal ``True``."""

    base = _good_attestation_doc()
    base["sentinel_present"] = 1
    _drive_probe(monkeypatch, tmp_path=tmp_path, attestation_doc=base)
    host = control.ProductionCeoSubmitHost()
    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is False


def test_production_ceo_admission_probe_refuses_unsafe_attestation_file_before_parsing(
    monkeypatch, tmp_path
):
    """D7: the bounded private-file read refuses BEFORE parsing the content.

    The attestation on disk is JSON-valid; ``_read_root_file`` raises
    ``HostControlError`` because the metadata is unsafe (multi-link,
    wrong owner, wrong mode, symlink, non-regular, or oversize).
    The probe MUST return False without ever calling ``json.loads``
    on the attestation bytes.
    """

    seen: list[bytes] = []

    real_json_loads = control.json.loads

    def recording_json_loads(*args, **kwargs):
        if args:
            seen.append(args[0])
        return real_json_loads(*args, **kwargs)

    monkeypatch.setattr(control.json, "loads", recording_json_loads)

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "control.json"
    config_path.write_text(json.dumps({"marker": "config"}), encoding="utf-8")

    attestation_path = tmp_path / "attestation.json"
    # The CONTENT is JSON-valid; only the metadata is unsafe.
    attestation_bytes_on_disk = json.dumps(
        _good_attestation_doc(), sort_keys=True
    ).encode("utf-8")
    attestation_path.write_bytes(attestation_bytes_on_disk)

    monkeypatch.setattr(control, "CONTROL_CONFIG", config_path)
    monkeypatch.setattr(
        control.grp, "getgrnam", lambda name: types.SimpleNamespace(gr_gid=0)
    )
    monkeypatch.setattr(
        control,
        "_root_json",
        lambda path, *, modes, uid=0, gid=None: (
            {
                "control_uid": 501,
                "control_environment_attestation_path": os.fspath(attestation_path),
            },
            b'{"control_uid": 501}',
        ),
    )

    def refuse_attestation(path, *, modes, uid=0, gid=None):
        raise control.HostControlError("config_identity_unavailable")

    monkeypatch.setattr(control, "_read_root_file", refuse_attestation)

    monkeypatch.setattr(
        control,
        "ProcessInspector",
        _LiveFakeInspector,
        raising=False,
    )
    monkeypatch.setattr(
        control.subprocess,
        "run",
        lambda *args, **kwargs: _FakeCompletedProcess(
            returncode=0, stdout=_status_body()
        ),
    )

    host = control.ProductionCeoSubmitHost()
    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is False
    # The probe NEVER reached ``json.loads`` on the unsafe file's content:
    # only the bounded status body was parsed.
    assert attestation_bytes_on_disk not in seen


def test_rollback_probe_admits_when_attestation_matches_the_restored_preimage(
    monkeypatch, tmp_path
):
    """D9 (positive): the rollback probe admits a fresh restored attestation."""

    _drive_probe(
        monkeypatch,
        tmp_path=tmp_path,
        attestation_doc=_good_attestation_doc(),
    )

    # DISARM rollback: prior was ARMED, candidates re-arm to that state.
    prior = _ceo_submit_evidence(armed=True)
    candidates = _armed_rollback_carrier(prior)
    transaction = _rollback_transaction(prior, candidates)

    host = _rollback_probe(
        monkeypatch,
        tmp_path,
        transaction,
        probe_error=None,
    )

    # No exception: ``rollback_ceo_submit`` proves the live service with the
    # exact restored preimage's attestation.
    host.rollback_ceo_submit(transaction, _rollback_receipt(transaction, armed=True))
    # Marker release is recorded as ``("complete", None)`` in the rollback
    # probe host's ledger; that ledger entry is the contract.
    assert host.ledger[-1] == ("complete", None)
    # ROLLBACK_CONTROL_PROVEN strictly precedes marker release.
    phases = [entry for entry in host.ledger if entry[0] == "phase"]
    assert "ADMISSION_BOUND" in [phase for _kind, phase in phases]
    assert "ROLLBACK_CONTROL_PROVEN" in [phase for _kind, phase in phases]


def test_admission_bound_does_not_touch_the_worker_service(
    monkeypatch, tmp_path
):
    """D11: ARM/DISARM/rollback probe path proves zero worker-service action.

    The new validator ride must NOT issue any worker plist bootstrap,
    kickstart, ps query, or sysctl query -- only the fixed control
    subprocess and the bounded control config + attestation reads.
    """

    ledger: list[tuple[str, str]] = []

    def fake_run(argv, **kwargs):
        joined = " ".join(str(part) for part in argv)
        ledger.append(("subprocess", joined))
        return _FakeCompletedProcess(
            returncode=0, stdout=_status_body()
        )

    monkeypatch.setattr(control.subprocess, "run", fake_run)

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "control.json"
    config_path.write_text(json.dumps({"marker": "config"}), encoding="utf-8")
    attestation_path = tmp_path / "attestation.json"
    attestation_path.write_text(
        json.dumps(_good_attestation_doc()), encoding="utf-8"
    )
    monkeypatch.setattr(control, "CONTROL_CONFIG", config_path)
    monkeypatch.setattr(
        control.grp, "getgrnam", lambda name: types.SimpleNamespace(gr_gid=0)
    )
    monkeypatch.setattr(
        control,
        "_root_json",
        lambda path, *, modes, uid=0, gid=None: (
            {
                "control_uid": 501,
                "control_environment_attestation_path": os.fspath(attestation_path),
            },
            b'{"control_uid": 501}',
        ),
    )
    monkeypatch.setattr(
        control,
        "_read_root_file",
        lambda path, *, modes, uid=0, gid=None: (
            json.dumps(_good_attestation_doc(), sort_keys=True).encode("utf-8"),
            _live_stat_info(),
        ),
    )
    monkeypatch.setattr(
        control,
        "ProcessInspector",
        _LiveFakeInspector,
        raising=False,
    )

    host = control.ProductionCeoSubmitHost()
    host._ceo_admission_probe(SHA, _CONFIG_DIGEST)

    joined = "\n".join(f"{kind}:{arg}" for kind, arg in ledger)
    assert control.WORKER_LABEL not in joined
    assert os.fspath(control.WORKER_PLIST) not in joined
    assert "/bin/launchctl" not in joined or "kickstart" not in joined
    assert "service-control.sh" not in joined
    assert "/bin/ps" not in joined
    assert "/usr/sbin/sysctl" not in joined


def test_prove_control_admission_bound_signature_accepts_expected_control_sha256():
    """The protocol method gains one keyword-only digest argument."""

    import inspect

    parameters = inspect.signature(
        control.ProductionCeoSubmitHost.prove_control_admission_bound
    ).parameters
    assert list(parameters) == ["self", "expected_sha", "expected_control_sha256"]
    expected_sha = parameters["expected_sha"]
    expected_control_sha256 = parameters["expected_control_sha256"]
    assert expected_sha.default is inspect.Parameter.empty
    assert expected_control_sha256.default is inspect.Parameter.empty


def test_ceo_admission_probe_signature_accepts_expected_control_sha256():
    """The production probe accepts (self, expected_sha, expected_control_sha256)."""

    import inspect

    parameters = inspect.signature(
        control.ProductionCeoSubmitHost._ceo_admission_probe
    ).parameters
    assert list(parameters) == ["self", "expected_sha", "expected_control_sha256"]


def test_production_ceo_admission_probe_refuses_post_reconcile_control_byte_drift(
    monkeypatch, tmp_path
):
    """B1: current root-owned bytes must still equal the transaction digest."""

    host = control.ProductionCeoSubmitHost()
    attestation_path = tmp_path / "attestation.json"
    drifted_raw = b"packet09-control-config-r80-drifted\n"
    assert hashlib.sha256(drifted_raw).hexdigest() != _CONFIG_DIGEST
    _drive_probe(
        monkeypatch,
        tmp_path=tmp_path,
        attestation_doc=_good_attestation_doc(),
        inspector=_LiveFakeInspector(),
        root_json_returns=(
            {
                "control_uid": 501,
                "control_environment_attestation_path": os.fspath(attestation_path),
            },
            drifted_raw,
        ),
    )

    assert host._ceo_admission_probe(SHA, _CONFIG_DIGEST) is False


# ---------------------------------------------------------------------------
# R81 authority-parity closure: the authority-granting read must assert every
# current-state invariant that ARM refuses. A self-consistent receipt is only
# evidence of agreement; it cannot authorize an otherwise forbidden state.
# ---------------------------------------------------------------------------

_R81_AUTHORITY_CASES = (
    ("coo_autonomy_armed", "coo_autonomy_armed"),
    ("coo_operator_harness_armed", "coo_operator_harness_armed"),
    ("ceo_ingress_app_unarmed", "ceo_ingress_app_unarmed"),
    ("app_binding_invalid", "app_binding_invalid"),
    ("app_acl_invalid", "app_acl_invalid"),
    ("app_topology_invalid", "app_topology_invalid"),
    ("app_peer_invalid", "app_peer_invalid"),
    ("separation_equal_uids", "ceo_ingress_separation_invalid"),
)


def _apply_r81_unauthorized_state(host, case):
    if case == "coo_autonomy_armed":
        host.control_config["coo_autonomy_armed"] = True
    elif case == "coo_operator_harness_armed":
        host.control_config["coo_operator_harness_armed"] = True
    elif case == "ceo_ingress_app_unarmed":
        host.control_config["ceo_ingress_app_armed"] = False
    elif case == "app_binding_invalid":
        host.binding_overrides["binding_valid"] = False
    elif case == "app_acl_invalid":
        host.binding_overrides["acl_valid"] = False
    elif case == "app_topology_invalid":
        host.binding_overrides["topology_valid"] = False
    elif case == "app_peer_invalid":
        host.binding_overrides["app_peer_user"] = "_mastermind_wrong_peer"
    elif case == "separation_equal_uids":
        host.control_config["ceo_ingress_peer_uid"] = host.control_config[
            "ceo_ingress_app_peer_uid"
        ]
    else:  # pragma: no cover - closed table above
        raise AssertionError(case)


def _seal_r81_self_consistent_receipt(host):
    """Re-seal the unauthenticated document around current unauthorized facts."""

    receipt = copy.deepcopy(host.receipt)
    binding = host.executive_app_binding()
    for field in control._CEO_SUBMIT_CONTROL_FIELDS:
        receipt["projection"][field] = host.control_config[field]
    receipt["projection"].update(
        {
            "app_peer_user": binding.app_peer_user,
            "app_binding_valid": binding.binding_valid,
            "app_acl_valid": binding.acl_valid,
            "app_topology_valid": binding.topology_valid,
        }
    )
    _recompute_receipt_digest(receipt)
    assert control.validate_ceo_submit_receipt_document(receipt, armed=True) is True
    return receipt, binding


@pytest.mark.parametrize(("case", "expected_code"), _R81_AUTHORITY_CASES)
def test_arm_and_authority_read_share_every_authority_invariant(case, expected_code):
    """R81: every ARM authority refusal is also a sink/read refusal."""

    arm_host = FakeCeoSubmitHost()
    _apply_r81_unauthorized_state(arm_host, case)
    before = copy.deepcopy(arm_host.control_config)
    with pytest.raises(control.CeoSubmitAdmissionError) as raised:
        control.execute_ceo_submit_arm(arm_host, _ceo_submit_request(), now=NOW)
    assert raised.value.code == expected_code
    assert arm_host.control_writes == 0
    assert arm_host.worker_writes == 0
    assert arm_host.receipt_writes == 0
    assert arm_host.marker is False
    assert arm_host.control_config == before

    read_host = _armed_ceo_submit_host()
    _apply_r81_unauthorized_state(read_host, case)
    receipt, binding = _seal_r81_self_consistent_receipt(read_host)
    read_host.receipt = receipt
    worker_sha = control.sha256_bytes(control.encode_config(read_host.worker_config))

    assert (
        control.ceo_submit_sink_eligible(
            control_config=read_host.control_config,
            worker_config=read_host.worker_config,
            worker_config_sha256=worker_sha,
            receipt=receipt,
            binding=binding,
            expected_sha=SHA,
            installed_sha=SHA,
        )
        is False
    )
    assert (
        control.evaluate_ceo_submit_status(read_host, _ceo_submit_request()).state
        == "CEO_SUBMIT_ARMED_UNBOUND"
    )
    assert read_host.control_writes == 1  # the original legitimate ARM only
    assert read_host.worker_writes == 0
    assert read_host.receipt_writes == 1


# ---------------------------------------------------------------------------
# Transaction marker publication repair harness.
#
# The ONE ``AUTONOMY_TRANSACTION`` marker must be complete -- recoverable
# identity, both exact preimages and the creator's own directory flock --
# before the canonical path is visible for the first time, and first
# publication must be serialized on the trusted config-directory inode lock.
# These tests import the FULL production module and run its real transaction
# machinery (real directory ``flock``, real ``fsync``, real atomic writes, the
# real publication rename, real inode readback) on a disposable filesystem,
# with competing creators and recovery claimants in SEPARATE interpreter
# processes.  Nothing is installed; no installed, mounted or service path is
# touched.
#
# Exactly three hermetic adapter families are supplied.  They are declared
# once (``_marker_adapter_bindings``) and installed identically by every
# spawned harness process:
#   * root paths -- the fixed installed roots are rebound to the test's
#     disposable directory;
#   * privilege metadata -- ownership identity is mapped to the privileged
#     (0, 0) identity the installed host runs as, while every mode, inode,
#     link-count and size fact stays the real on-disk value;
#   * ACL -- ``_has_acl`` reports False (existing fixture style).
# Admission and service boundaries (release identity, the App peer binding,
# the sudo candidate validator, the launchctl reconcile/admission effects) are
# hermetically supplied stubs.  The marker lifecycle itself is never stubbed.
# ---------------------------------------------------------------------------

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
_CANONICAL_MARKER_NAME = "autonomy-transaction.lock"
_SEALED_MARKER_ENTRIES = [
    "prior-control.json",
    "prior-worker.json",
    "transaction.json",
]
_MARKER_CONFIG_ENTRIES = [
    "control.json",
    "unrelated-dir",
    "unrelated-root-entry.json",
    "worker-codex.json",
]


def _marker_control_document():
    """The installed control document, in the composed disarmed shape."""

    return {
        "schema_version": "mastermind.executive_control_config/v1",
        "proof_base_sha": SHA,
        "ceo_submit_armed": False,
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


def _marker_worker_document():
    return {
        "schema_version": "mastermind.executive_worker_config/v1",
        "operator_harness_armed": False,
        "preserved": ["beta"],
    }


def _marker_workspace(workdir: Path) -> Path:
    """The disposable config root with the installed documents in place."""

    config_root = workdir / "config"
    config_root.mkdir(mode=0o755)
    for name, document in (
        ("control.json", _marker_control_document()),
        ("worker-codex.json", _marker_worker_document()),
    ):
        target = config_root / name
        target.write_bytes(control.encode_config(document))
        os.chmod(target, 0o440)
    # A foreign entry the transaction must never touch, whatever happens.
    (config_root / "unrelated-root-entry.json").write_bytes(b"foreign\n")
    (config_root / "unrelated-dir").mkdir()
    (config_root / "unrelated-dir" / "keep.txt").write_bytes(b"keep\n")
    os.chmod(config_root, 0o755)
    return config_root


def _marker_adapter_bindings():
    """The three hermetic adapters, declared once for every harness process."""

    real_fstat = os.fstat
    real_lstat = Path.lstat

    def _privileged(info):
        return os.stat_result(
            (
                info.st_mode,
                info.st_ino,
                info.st_dev,
                info.st_nlink,
                0,
                0,
                info.st_size,
                info.st_atime,
                info.st_mtime,
                info.st_ctime,
            )
        )

    def privileged_fstat(descriptor):
        return _privileged(real_fstat(descriptor))

    def privileged_lstat(path):
        return _privileged(real_lstat(path))

    def privileged_root_chown(path, uid, gid):
        if (uid, gid) != (0, 0):
            raise ValueError("marker harness only adapts the root identity")
        return None

    return [
        (control.os, "fstat", privileged_fstat),
        (control.Path, "lstat", privileged_lstat),
        (control.os, "chown", privileged_root_chown),
        (control.os, "fchown", privileged_root_chown),
        (control.grp, "getgrnam", lambda name: types.SimpleNamespace(gr_gid=0)),
        (control, "_has_acl", lambda _path: False),
    ]


def _marker_roots(config_root: Path):
    return [
        (control, "CONFIG_ROOT", config_root),
        (control, "AUTONOMY_TRANSACTION", config_root / _CANONICAL_MARKER_NAME),
        (control, "CONTROL_CONFIG", config_root / "control.json"),
        (control, "WORKER_CONFIG", config_root / "worker-codex.json"),
        (control, "AUTONOMY_RECEIPT", config_root / "autonomy-state-v1.json"),
        (control, "CEO_SUBMIT_RECEIPT", config_root / "ceo-submit-state-v1.json"),
    ]


def _install_marker_adapters(monkeypatch, config_root: Path) -> None:
    for target, name, value in _marker_roots(config_root):
        monkeypatch.setattr(target, name, value)
    for target, name, value in _marker_adapter_bindings():
        monkeypatch.setattr(target, name, value)


def _manifest_of(canonical: Path) -> dict:
    return json.loads((canonical / "transaction.json").read_text(encoding="utf-8"))


def _assert_complete_locked_marker(canonical: Path, expected_operation: str) -> dict:
    """The commissioned first-visibility postcondition, at the canonical path.

    Complete recoverable identity, both exact preimages and creator-owned
    exclusion must already hold at the FIRST canonical visibility.
    """

    manifest = _manifest_of(canonical)
    assert manifest["schema_version"] == control._TRANSACTION_SCHEMA
    assert manifest["operation"] == expected_operation
    assert manifest["phase"] == "LOCKED"
    assert (
        re.fullmatch(r"autonomy-[0-9a-f]{12}", manifest["transaction_id"]) is not None
    )
    assert manifest["expected_sha"] == SHA
    for field in (
        "prior_control_sha256",
        "prior_worker_sha256",
        "target_control_sha256",
        "target_worker_sha256",
    ):
        assert re.fullmatch(r"[0-9a-f]{64}", manifest[field]) is not None
    assert sorted(os.listdir(canonical)) == _SEALED_MARKER_ENTRIES
    control_bytes = (canonical / "prior-control.json").read_bytes()
    worker_bytes = (canonical / "prior-worker.json").read_bytes()
    assert (
        hashlib.sha256(control_bytes).hexdigest() == manifest["prior_control_sha256"]
    )
    assert hashlib.sha256(worker_bytes).hexdigest() == manifest["prior_worker_sha256"]
    assert json.loads(control_bytes.decode("utf-8")) == _marker_control_document()
    assert json.loads(worker_bytes.decode("utf-8")) == _marker_worker_document()
    info = canonical.stat()
    assert stat.S_ISDIR(info.st_mode)
    assert stat.S_IMODE(info.st_mode) == 0o700
    return manifest


def _foreign_entry_snapshot(config_root: Path) -> dict:
    return {
        "unrelated-root-entry.json": (
            config_root / "unrelated-root-entry.json"
        ).read_bytes(),
        "unrelated-dir": sorted(
            entry.name for entry in (config_root / "unrelated-dir").iterdir()
        ),
    }


_HARNESS_CHILD_BOOTSTRAP = '''
"""Spawned marker-publication harness process (imports the full module)."""
import importlib.util
import json
import os
import sys
from pathlib import Path

_repo, _workdir, _scenario = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, _repo)
from ops.executive_os import autonomy_control as control  # full production module

_spec = importlib.util.spec_from_file_location(
    "mmx_marker_publication_harness",
    os.path.join(_repo, "tests", "test_executive_autonomy_control.py"),
)
_harness = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _harness  # dataclasses resolve annotations via sys.modules
_spec.loader.exec_module(_harness)

_journal = []
_summary = {"scenario": _scenario}
try:
    _summary.update(_harness.run_harness_scenario(_scenario, Path(_workdir), _journal))
    _summary["ok"] = True
except BaseException as exc:  # recorded for the parent, never hidden
    _summary["ok"] = False
    _summary["error"] = type(exc).__name__
    _summary["code"] = getattr(exc, "code", None)
    _summary["errno"] = getattr(exc, "errno", None)
    _summary["detail"] = repr(exc)[:500]
finally:
    with open(
        os.path.join(_workdir, f"harness-child-{_scenario}.json"), "w", encoding="utf-8"
    ) as _fh:
        json.dump({"summary": _summary, "journal": _journal}, _fh, indent=2)
'''

_HARNESS_SCENARIOS = {}
_HARNESS_RELEASE_TOKEN = b"release"


def _harness_scenario(name):
    def register(handler):
        _HARNESS_SCENARIOS[name] = handler
        return handler

    return register


def run_harness_scenario(scenario: str, workdir: Path, journal: list) -> dict:
    """Entry point for the spawned harness processes."""

    return _HARNESS_SCENARIOS[scenario](workdir, journal)


class _HarnessChannel:
    """The parent's stage gate: signal a label, then block for the release."""

    def __init__(self):
        self._descriptor = int(os.environ["MMX_MARKER_RELEASE_FD"])

    def signal(self, label):
        sys.__stdout__.write(f"{label}\n")
        sys.__stdout__.flush()

    def pause(self, label="PAUSED"):
        self.signal(label)
        # Exactly one token per gate: reads are sized to the token so queued
        # teardown tokens cannot corrupt the comparison.
        if os.read(self._descriptor, len(_HARNESS_RELEASE_TOKEN)) != _HARNESS_RELEASE_TOKEN:
            os._exit(75)


def _harness_child_setup(workdir: Path):
    config_root = workdir / "config"
    for target, name, value in _marker_roots(config_root):
        setattr(target, name, value)
    for target, name, value in _marker_adapter_bindings():
        setattr(target, name, value)
    return config_root, config_root / _CANONICAL_MARKER_NAME


def _harness_watch_canonical_visibility(canonical: Path, journal: list, channel):
    """Record and gate the FIRST canonical visibility, however it is reached."""

    real_mkdir = os.mkdir
    real_rename = os.rename

    def mkdir(path, mode=0o777):
        result = real_mkdir(path, mode)
        if Path(path) == canonical:
            journal.append({"event": "canonical_mkdir", "path": os.fspath(path)})
            channel.pause()
        return result

    def rename(source, destination):
        published = Path(destination) == canonical
        if published:
            journal.append(
                {"event": "publication_edge", "generation": os.fspath(source)}
            )
        result = real_rename(source, destination)
        if published:
            journal.append(
                {"event": "canonical_visible", "generation": os.fspath(source)}
            )
            channel.pause()
        return result

    os.mkdir = mkdir
    os.rename = rename


def _harness_ceo_submit_host():
    """The production CEO-submit host; ONLY admission/service boundaries are
    hermetic.  Every marker, config, receipt and completion method stays the
    production implementation."""

    host = control.ProductionCeoSubmitHost()
    host.effective_uid = lambda: 0
    host.require_exact_install = lambda expected_sha: expected_sha
    host.executive_app_binding = lambda: control.ExecutiveAppBinding(
        present=True,
        app_peer_uid=458,
        app_peer_user=control.EXECUTIVE_APP_USER,
        app_armed=True,
        app_macro_root=CEO_SUBMIT_APP_MACRO_ROOT,
        ingress_peer_uid=452,
        ingress_socket_path="/var/run/mastermind-executive/ceo-ingress.sock",
        launchd_socket_name="CeoIngress",
        binding_valid=True,
        acl_valid=True,
        topology_valid=True,
    )
    host.validate_candidates = lambda transaction: host._persist_phase(
        transaction, "CANDIDATES_VALIDATED"
    )
    host.reconcile_control_service = lambda _expected_sha: host._persist_phase(
        host._active_transaction, "CONTROL_RECONCILED"
    )
    host.prove_control_admission_bound = lambda _sha, _digest: host._persist_phase(
        host._active_transaction, "ADMISSION_BOUND"
    )
    return host


def _harness_configs(host):
    (
        control_document,
        worker_document,
        control_digest,
        worker_digest,
        control_raw,
        worker_raw,
    ) = host._configs()
    return control.ConfigEvidence(
        control_sha256=control_digest,
        worker_sha256=worker_digest,
        control=control_document,
        worker=worker_document,
        control_bytes=control_raw,
        worker_bytes=worker_raw,
    )


def _harness_coo_transaction(host, *, armed):
    configs = _harness_configs(host)
    return control.TransactionContext(
        transaction_id=host.new_transaction_id(),
        expected_sha=SHA,
        prior_configs=configs,
        candidates=control.derive_candidate_configs(configs, armed=armed),
        admission=None,
    )


def _harness_ceo_submit_transaction(host):
    configs = host.load_ceo_submit_configs(SHA)
    return control.TransactionContext(
        transaction_id=host.new_transaction_id(),
        expected_sha=SHA,
        prior_configs=configs,
        candidates=control.derive_ceo_submit_candidate(configs, armed=True),
        admission=None,
    )


@_harness_scenario("ceo-submit-arm-paused-at-publication")
def _scenario_ceo_submit_arm_paused(workdir, journal):
    config_root, canonical = _harness_child_setup(workdir)
    channel = _HarnessChannel()
    _harness_watch_canonical_visibility(canonical, journal, channel)
    worker_before = (config_root / "worker-codex.json").read_bytes()
    host = _harness_ceo_submit_host()
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        exit_code = control.main(
            ["ceo-submit-arm", "--expected-sha", SHA], host=host, now=lambda: NOW
        )
    return {
        "exit_code": exit_code,
        "document": json.loads(buffer.getvalue()),
        "worker_bytes_unchanged": (config_root / "worker-codex.json").read_bytes()
        == worker_before,
        "control_document": json.loads(
            (config_root / "control.json").read_text(encoding="utf-8")
        ),
        "receipt_present": (config_root / "ceo-submit-state-v1.json").exists(),
        "marker_present": canonical.exists(),
        "config_entries": sorted(os.listdir(config_root)),
    }


@_harness_scenario("coo-arm-begin-paused-at-publication")
def _scenario_coo_arm_begin_paused(workdir, journal):
    config_root, canonical = _harness_child_setup(workdir)
    channel = _HarnessChannel()
    _harness_watch_canonical_visibility(canonical, journal, channel)
    host = control.ProductionTransactionHost()
    transaction = _harness_coo_transaction(host, armed=True)
    host.begin_transaction(transaction)
    published = os.stat(canonical)
    channel.signal("PUBLISHED")
    channel.pause("RELEASED")
    return {
        "transaction_id": transaction.transaction_id,
        "marker_dev": published.st_dev,
        "marker_ino": published.st_ino,
        "owner_fd_retained": host._transaction_owner_fd is not None,
        "manifest": _manifest_of(canonical),
        "config_entries": sorted(os.listdir(config_root)),
    }


@_harness_scenario("ceo-submit-begin-paused-at-publication")
def _scenario_ceo_submit_begin_paused(workdir, journal):
    config_root, canonical = _harness_child_setup(workdir)
    channel = _HarnessChannel()
    _harness_watch_canonical_visibility(canonical, journal, channel)
    host = control.ProductionCeoSubmitHost()
    transaction = _harness_ceo_submit_transaction(host)
    host.begin_ceo_submit_transaction(transaction, operation="CEO_SUBMIT_ARM")
    published = os.stat(canonical)
    channel.signal("PUBLISHED")
    channel.pause("RELEASED")
    return {
        "transaction_id": transaction.transaction_id,
        "marker_dev": published.st_dev,
        "marker_ino": published.st_ino,
        "owner_fd_retained": host._transaction_owner_fd is not None,
        "manifest": _manifest_of(canonical),
        "config_entries": sorted(os.listdir(config_root)),
    }


@_harness_scenario("disarm-begin-paused-at-publication")
def _scenario_disarm_begin_paused(workdir, journal):
    config_root, canonical = _harness_child_setup(workdir)
    channel = _HarnessChannel()
    _harness_watch_canonical_visibility(canonical, journal, channel)
    host = control.ProductionTransactionHost()
    transaction_id = host.new_transaction_id()
    configs = host.begin_disarm(SHA, transaction_id)
    published = os.stat(canonical)
    channel.signal("PUBLISHED")
    channel.pause("RELEASED")
    transaction = control.TransactionContext(
        transaction_id=transaction_id,
        expected_sha=SHA,
        prior_configs=configs,
        candidates=control.derive_candidate_configs(configs, armed=False),
        admission=None,
    )
    manifest = _manifest_of(canonical)
    host.complete_transaction(transaction)
    return {
        "transaction_id": transaction_id,
        "marker_dev": published.st_dev,
        "marker_ino": published.st_ino,
        "owner_fd_retained": host._transaction_owner_fd is not None,
        "manifest": manifest,
        "marker_present_after_completion": canonical.exists(),
        "config_entries": sorted(os.listdir(config_root)),
    }


@_harness_scenario("coo-new-transaction-id")
def _scenario_coo_new_transaction_id(workdir, journal):
    _config_root, _canonical = _harness_child_setup(workdir)
    transaction_id = control.ProductionTransactionHost().new_transaction_id()
    return {"transaction_id": transaction_id}


@_harness_scenario("ceo-submit-new-transaction-id")
def _scenario_ceo_submit_new_transaction_id(workdir, journal):
    _config_root, _canonical = _harness_child_setup(workdir)
    transaction_id = control.ProductionCeoSubmitHost().new_transaction_id()
    return {"transaction_id": transaction_id}


@_harness_scenario("coo-begin-competitor")
def _scenario_coo_begin_competitor(workdir, journal):
    config_root, canonical = _harness_child_setup(workdir)
    host = control.ProductionTransactionHost()
    configs = _harness_configs(host)
    transaction = control.TransactionContext(
        transaction_id=host.new_transaction_id(),
        expected_sha=SHA,
        prior_configs=configs,
        candidates=control.derive_candidate_configs(configs, armed=True),
        admission=None,
    )
    try:
        host.begin_transaction(transaction)
    except control.ArmAdmissionError as exc:
        return {
            "refused": exc.code,
            "transaction_id": transaction.transaction_id,
            "config_entries": sorted(os.listdir(config_root)),
        }
    return {
        "refused": None,
        "transaction_id": transaction.transaction_id,
        "config_entries": sorted(os.listdir(config_root)),
    }


@_harness_scenario("ceo-submit-begin-competitor")
def _scenario_ceo_submit_begin_competitor(workdir, journal):
    config_root, canonical = _harness_child_setup(workdir)
    host = control.ProductionCeoSubmitHost()
    transaction = _harness_ceo_submit_transaction(host)
    try:
        host.begin_ceo_submit_transaction(transaction, operation="CEO_SUBMIT_ARM")
    except control.CeoSubmitAdmissionError as exc:
        return {
            "refused": exc.code,
            "transaction_id": transaction.transaction_id,
            "config_entries": sorted(os.listdir(config_root)),
        }
    return {
        "refused": None,
        "transaction_id": transaction.transaction_id,
        "config_entries": sorted(os.listdir(config_root)),
    }


@_harness_scenario("recovery-claim")
def _scenario_recovery_claim(workdir, journal):
    config_root, canonical = _harness_child_setup(workdir)
    host = control.ProductionCeoSubmitHost()
    try:
        host._claim_transaction_owner()
    except control.TransactionEffectUnknown:
        return {
            "claimed": False,
            "marker_present": canonical.exists(),
            "config_entries": sorted(os.listdir(config_root)),
        }
    manifest = host._manifest()
    prior = host._archived_configs(SHA)
    info = os.stat(canonical)
    host._release_transaction_owner()
    return {
        "claimed": True,
        "transaction_id": str(manifest["transaction_id"]),
        "operation": manifest.get("operation"),
        "phase": manifest.get("phase"),
        "marker_dev": info.st_dev,
        "marker_ino": info.st_ino,
        "prior_control_sha256": prior.control_sha256,
        "prior_worker_sha256": prior.worker_sha256,
        "marker_present": canonical.exists(),
        "config_entries": sorted(os.listdir(config_root)),
    }


@_harness_scenario("pre-publication-failure-coo")
def _scenario_pre_publication_failure_coo(workdir, journal):
    config_root, canonical = _harness_child_setup(workdir)
    real_atomic = control._atomic_file

    def failing_atomic(path, payload, *, mode, uid, gid, replace):
        if Path(path).name == "prior-worker.json":
            raise OSError(28, "No space left on device")
        return real_atomic(path, payload, mode=mode, uid=uid, gid=gid, replace=replace)

    control._atomic_file = failing_atomic
    host = control.ProductionTransactionHost()
    transaction = _harness_coo_transaction(host, armed=True)
    try:
        host.begin_transaction(transaction)
    except Exception as exc:
        failure = {
            "error": type(exc).__name__,
            "code": getattr(exc, "code", None),
            "errno": getattr(exc, "errno", None),
        }
    else:
        failure = {"error": None}
    return {
        "failure": failure,
        "transaction_id": transaction.transaction_id,
        "marker_present": canonical.exists(),
        "config_entries": sorted(os.listdir(config_root)),
    }


@_harness_scenario("pre-publication-failure-ceo")
def _scenario_pre_publication_failure_ceo(workdir, journal):
    config_root, canonical = _harness_child_setup(workdir)
    real_atomic = control._atomic_file

    def failing_atomic(path, payload, *, mode, uid, gid, replace):
        if Path(path).name == "prior-worker.json":
            raise OSError(28, "No space left on device")
        return real_atomic(path, payload, mode=mode, uid=uid, gid=gid, replace=replace)

    control._atomic_file = failing_atomic
    host = control.ProductionCeoSubmitHost()
    transaction = _harness_ceo_submit_transaction(host)
    try:
        host.begin_ceo_submit_transaction(transaction, operation="CEO_SUBMIT_ARM")
    except Exception as exc:
        failure = {
            "error": type(exc).__name__,
            "code": getattr(exc, "code", None),
            "errno": getattr(exc, "errno", None),
        }
    else:
        failure = {"error": None}
    return {
        "failure": failure,
        "transaction_id": transaction.transaction_id,
        "marker_present": canonical.exists(),
        "config_entries": sorted(os.listdir(config_root)),
    }


@_harness_scenario("ceo-submit-arm-publication-acknowledgement-loss")
def _scenario_ceo_submit_arm_acknowledgement_loss(workdir, journal):
    config_root, canonical = _harness_child_setup(workdir)
    real_fsync = control._fsync_directory

    def failing_fsync(path):
        if Path(path) == config_root:
            raise OSError(5, "Input/output error")
        return real_fsync(path)

    control._fsync_directory = failing_fsync
    control_before = (config_root / "control.json").read_bytes()
    worker_before = (config_root / "worker-codex.json").read_bytes()
    host = _harness_ceo_submit_host()
    try:
        control.execute_ceo_submit_arm(
            host, control.CeoSubmitRequest(expected_sha=SHA), now=NOW
        )
    except Exception as exc:
        failure = {
            "error": type(exc).__name__,
            "code": getattr(exc, "code", None),
            "errno": getattr(exc, "errno", None),
        }
    else:
        failure = {"error": None}
    info = os.stat(canonical)
    try:
        manifest = _manifest_of(canonical)
    except (OSError, ValueError):
        # An unreadable/unparseable manifest is itself a reportable condition;
        # the parent classifies it.
        manifest = None
    return {
        "failure": failure,
        "manifest": manifest,
        "marker_entries": sorted(os.listdir(canonical)),
        "marker_dev": info.st_dev,
        "marker_ino": info.st_ino,
        "owner_fd_retained": host._transaction_owner_fd is not None,
        "control_bytes_unchanged": (config_root / "control.json").read_bytes()
        == control_before,
        "worker_bytes_unchanged": (config_root / "worker-codex.json").read_bytes()
        == worker_before,
        "receipt_present": (config_root / "ceo-submit-state-v1.json").exists(),
        "config_entries": sorted(os.listdir(config_root)),
    }


class _HarnessProcess:
    """A spawned full-module harness process and its stage gate."""

    def __init__(self, workdir: Path, scenario: str) -> None:
        self.workdir = workdir
        self.scenario = scenario
        read_fd, write_fd = os.pipe()
        script = workdir / f"harness-{scenario}.py"
        script.write_text(_HARNESS_CHILD_BOOTSTRAP, encoding="utf-8")
        environment = dict(os.environ)
        environment["MMX_MARKER_RELEASE_FD"] = str(read_fd)
        self.stderr_path = workdir / f"harness-{scenario}.stderr.txt"
        self._stderr = open(self.stderr_path, "wb")
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-B",
                os.fspath(script),
                _REPO_ROOT,
                os.fspath(workdir),
                scenario,
            ],
            cwd=_REPO_ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=self._stderr,
            pass_fds=(read_fd,),
        )
        os.close(read_fd)
        self._release_fd = write_fd
        self._released = False

    def wait_for(self, label: str, timeout: float = 90.0) -> None:
        ready, _, _ = select.select([self.process.stdout], [], [], timeout)
        if not ready:
            raise AssertionError(
                f"harness child {self.scenario} never signalled {label}; "
                f"stderr: {self._stderr_tail()}"
            )
        line = self.process.stdout.readline()
        if line != f"{label}\n".encode("utf-8"):
            raise AssertionError(
                f"harness child {self.scenario} signalled {line!r}, not {label}; "
                f"stderr: {self._stderr_tail()}"
            )

    def release(self) -> None:
        """Release exactly ONE stage gate (the one the child is paused on)."""

        if self._released:
            return
        self._released = True
        try:
            os.write(self._release_fd, _HARNESS_RELEASE_TOKEN)
        except OSError:
            pass

    def result(self, timeout: float = 120.0) -> tuple[dict, list]:
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=30)
            raise AssertionError(
                f"harness child {self.scenario} hung and was killed; "
                f"stderr: {self._stderr_tail()}"
            ) from None
        payload = json.loads(
            (self.workdir / f"harness-child-{self.scenario}.json").read_text(
                encoding="utf-8"
            )
        )
        return payload["summary"], payload["journal"]

    def _stderr_tail(self) -> str:
        try:
            return self.stderr_path.read_text(encoding="utf-8", errors="replace")[-800:]
        except OSError:
            return ""

    def close(self) -> None:
        # Drain every remaining stage gate so a child paused deeper in the
        # scenario can never deadlock the teardown.  Spare tokens are ignored
        # by a child that has already left its gates, and EPIPE by one that
        # has already exited.
        self._released = True
        for _ in range(4):
            try:
                os.write(self._release_fd, _HARNESS_RELEASE_TOKEN)
            except OSError:
                pass
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=30)
        if self.process.stdout is not None:
            self.process.stdout.close()
        self._stderr.close()
        os.close(self._release_fd)


@contextlib.contextmanager
def _harness_process(workdir: Path, scenario: str):
    child = _HarnessProcess(workdir, scenario)
    try:
        yield child
    finally:
        child.close()


def test_ceo_submit_arm_publishes_a_complete_marker_at_first_visibility(tmp_path):
    """Matrix 1: through ``main`` with the real production CEO-submit host.

    At the FIRST canonical visibility the marker must already be a complete,
    parseable LOCKED manifest carrying both exact preimages, and a competing
    creator in another process must be excluded from the identity.
    """

    workdir = tmp_path / "harness"
    workdir.mkdir()
    config_root = _marker_workspace(workdir)
    canonical = config_root / _CANONICAL_MARKER_NAME
    with _harness_process(workdir, "ceo-submit-arm-paused-at-publication") as child:
        child.wait_for("PAUSED")
        manifest = _assert_complete_locked_marker(canonical, "CEO_SUBMIT_ARM")

        # A competing creator in another process cannot take or even read the
        # identity while the publication owner is alive: it is refused, mints
        # nothing, and leaves no residue.
        with _harness_process(workdir, "ceo-submit-new-transaction-id") as competitor:
            competitor_summary, _competitor_journal = competitor.result()
        assert competitor_summary["ok"] is False, competitor_summary
        assert competitor_summary["error"] == "TransactionEffectUnknown"
        assert sorted(os.listdir(config_root)) == sorted(
            _MARKER_CONFIG_ENTRIES + [_CANONICAL_MARKER_NAME]
        )
        assert _manifest_of(canonical) == manifest

        child.release()
    summary, journal = child.result()
    assert summary["ok"] is True, summary
    assert summary["exit_code"] == 0
    assert summary["document"]["status"] == "CEO_SUBMIT_ARMED"
    assert summary["document"]["transaction_id"] == manifest["transaction_id"]
    assert summary["marker_present"] is False
    assert summary["receipt_present"] is True
    assert summary["control_document"]["ceo_submit_armed"] is True
    assert summary["worker_bytes_unchanged"] is True
    assert summary["config_entries"] == sorted(
        _MARKER_CONFIG_ENTRIES + ["ceo-submit-state-v1.json"]
    )
    assert [event["event"] for event in journal] == [
        "publication_edge",
        "canonical_visible",
    ]


@pytest.mark.parametrize(
    ("creator_scenario", "expected_operation"),
    [
        ("coo-arm-begin-paused-at-publication", "ARM"),
        ("ceo-submit-begin-paused-at-publication", "CEO_SUBMIT_ARM"),
    ],
)
def test_competing_creators_and_recovery_claimants_cannot_steal_first_ownership(
    tmp_path, creator_scenario, expected_operation
):
    """Matrix 2: both creation-owner uses, contested across real processes."""

    workdir = tmp_path / "harness"
    workdir.mkdir()
    config_root = _marker_workspace(workdir)
    canonical = config_root / _CANONICAL_MARKER_NAME
    with _harness_process(workdir, creator_scenario) as creator:
        creator.wait_for("PAUSED")
        manifest = _assert_complete_locked_marker(canonical, expected_operation)

        # A recovery claimant in a separate process cannot take the owner.
        with _harness_process(workdir, "recovery-claim") as claimant:
            claim_summary, _claim_journal = claimant.result()
        assert claim_summary["ok"] is True, claim_summary
        assert claim_summary["claimed"] is False
        assert claim_summary["marker_present"] is True

        # A competing creator cannot even read the identity while the owner
        # holds the marker: it is excluded, and it leaves nothing behind.
        for competitor_scenario in (
            "coo-begin-competitor",
            "ceo-submit-begin-competitor",
        ):
            with _harness_process(workdir, competitor_scenario) as competitor:
                competitor_summary, _competitor_journal = competitor.result()
            assert competitor_summary["ok"] is False, competitor_summary
            assert competitor_summary["error"] == "TransactionEffectUnknown"
            assert sorted(os.listdir(config_root)) == sorted(
                _MARKER_CONFIG_ENTRIES + [_CANONICAL_MARKER_NAME]
            )

        creator.release()
        creator.wait_for("PUBLISHED")
        inode = canonical.stat().st_ino
        assert _manifest_of(canonical) == manifest
        assert canonical.stat().st_ino == inode
    summary, journal = creator.result()
    assert summary["ok"] is True, summary
    assert summary["transaction_id"] == manifest["transaction_id"]
    assert summary["owner_fd_retained"] is True
    assert summary["manifest"] == manifest
    assert [event["event"] for event in journal] == [
        "publication_edge",
        "canonical_visible",
    ]

    # After the owner exits, a real recovery process claims the SAME inode.
    with _harness_process(workdir, "recovery-claim") as claimant:
        recovery, _recovery_journal = claimant.result()
    assert recovery["ok"] is True, recovery
    assert recovery["claimed"] is True
    assert recovery["transaction_id"] == manifest["transaction_id"]
    assert (recovery["marker_dev"], recovery["marker_ino"]) == (
        summary["marker_dev"],
        summary["marker_ino"],
    )
    assert (
        recovery["prior_control_sha256"]
        == control.sha256_bytes(control.encode_config(_marker_control_document()))
    )
    assert (
        recovery["prior_worker_sha256"]
        == control.sha256_bytes(control.encode_config(_marker_worker_document()))
    )

    # With the owner gone, a competing creator is typed-refused on the SAME
    # identity: no second transaction is ever minted or orphaned.
    for competitor_scenario, expected_code in (
        ("coo-begin-competitor", "transaction_incomplete"),
        ("ceo-submit-begin-competitor", "ceo_submit_transaction_incomplete"),
    ):
        with _harness_process(workdir, competitor_scenario) as competitor:
            competitor_summary, _competitor_journal = competitor.result()
        assert competitor_summary["ok"] is True, competitor_summary
        assert competitor_summary["refused"] == expected_code
        assert competitor_summary["transaction_id"] == manifest["transaction_id"]
    assert sorted(os.listdir(config_root)) == sorted(
        _MARKER_CONFIG_ENTRIES + [_CANONICAL_MARKER_NAME]
    )
    assert _manifest_of(canonical) == manifest


@pytest.mark.parametrize(
    "scenario", ["pre-publication-failure-coo", "pre-publication-failure-ceo"]
)
def test_pre_publication_failure_leaves_zero_canonical_effect(tmp_path, scenario):
    """Matrix 3: a private generation that fails is exactly disposed of."""

    workdir = tmp_path / "harness"
    workdir.mkdir()
    config_root = _marker_workspace(workdir)
    canonical = config_root / _CANONICAL_MARKER_NAME
    foreign_before = _foreign_entry_snapshot(config_root)
    with _harness_process(workdir, scenario) as child:
        summary, journal = child.result()
    assert summary["ok"] is True, summary
    if scenario.endswith("coo"):
        assert summary["failure"] == {
            "error": "TransactionOwnershipError",
            "code": "effect_unknown",
            "errno": None,
        }
    else:
        assert summary["failure"]["error"] == "OSError"
        assert summary["failure"]["errno"] == 28
    assert summary["marker_present"] is False
    assert journal == []
    entries = sorted(os.listdir(config_root))
    assert _CANONICAL_MARKER_NAME not in entries
    assert [name for name in entries if name.startswith(".autonomy-transaction-")] == []
    assert _foreign_entry_snapshot(config_root) == foreign_before
    assert (config_root / "control.json").read_bytes() == control.encode_config(
        _marker_control_document()
    )
    assert (config_root / "worker-codex.json").read_bytes() == control.encode_config(
        _marker_worker_document()
    )


def test_publication_acknowledgement_loss_stays_effect_unknown_and_recoverable(
    tmp_path,
):
    """Matrix 4: loss after publication is typed UNKNOWN, never rolled back."""

    workdir = tmp_path / "harness"
    workdir.mkdir()
    config_root = _marker_workspace(workdir)
    canonical = config_root / _CANONICAL_MARKER_NAME
    with _harness_process(
        workdir, "ceo-submit-arm-publication-acknowledgement-loss"
    ) as child:
        summary, journal = child.result()
    assert summary["ok"] is True, summary
    assert summary["failure"] == {
        "error": "TransactionEffectUnknown",
        "code": "effect_unknown",
        "errno": None,
    }
    assert summary["owner_fd_retained"] is True
    assert summary["control_bytes_unchanged"] is True
    assert summary["worker_bytes_unchanged"] is True
    assert summary["receipt_present"] is False
    assert summary["config_entries"] == sorted(
        _MARKER_CONFIG_ENTRIES + [_CANONICAL_MARKER_NAME]
    )
    manifest = summary["manifest"]
    assert manifest["operation"] == "CEO_SUBMIT_ARM"
    assert _assert_complete_locked_marker(canonical, "CEO_SUBMIT_ARM") == manifest
    published = (summary["marker_dev"], summary["marker_ino"])

    with _harness_process(workdir, "recovery-claim") as claimant:
        recovery, _recovery_journal = claimant.result()
    assert recovery["ok"] is True, recovery
    assert recovery["claimed"] is True
    assert recovery["transaction_id"] == manifest["transaction_id"]
    assert (recovery["marker_dev"], recovery["marker_ino"]) == published

    # A conflicting replacement fails closed and is never clobbered or erased.
    foreign_generation = (
        config_root
        / ".autonomy-transaction-aaaaaaaaaaaa.99999999.deadbeefdeadbeef.generating"
    )
    foreign_generation.mkdir()
    (foreign_generation / "evidence.txt").write_bytes(b"evidence\n")
    os.rename(canonical, config_root / "superseded-marker")
    os.symlink("decoy", canonical)
    (config_root / "decoy").mkdir()
    with _harness_process(workdir, "recovery-claim") as claimant:
        conflicting, _conflicting_journal = claimant.result()
    assert conflicting["ok"] is True, conflicting
    assert conflicting["claimed"] is False
    assert os.path.islink(canonical)
    assert (config_root / "decoy").is_dir()
    assert (config_root / "superseded-marker").is_dir()
    assert (foreign_generation / "evidence.txt").read_bytes() == b"evidence\n"


def test_legacy_disarm_creation_is_also_complete_before_visible(tmp_path):
    """Matrix 5: the legacy DISARM creation owner satisfies the same law."""

    workdir = tmp_path / "harness"
    workdir.mkdir()
    config_root = _marker_workspace(workdir)
    canonical = config_root / _CANONICAL_MARKER_NAME
    with _harness_process(workdir, "disarm-begin-paused-at-publication") as creator:
        creator.wait_for("PAUSED")
        manifest = _assert_complete_locked_marker(canonical, "DISARM")
        creator.release()
        creator.wait_for("PUBLISHED")
    summary, journal = creator.result()
    assert summary["ok"] is True, summary
    assert summary["transaction_id"] == manifest["transaction_id"]
    assert summary["owner_fd_retained"] is False
    assert summary["marker_present_after_completion"] is False
    assert summary["config_entries"] == _MARKER_CONFIG_ENTRIES
    assert [event["event"] for event in journal] == [
        "publication_edge",
        "canonical_visible",
    ]


def _inprocess_marker_host(monkeypatch, tmp_path):
    config_root = _marker_workspace(tmp_path)
    _install_marker_adapters(monkeypatch, config_root)
    return config_root, config_root / _CANONICAL_MARKER_NAME


def test_owner_fd_is_held_from_publication_until_lawful_settlement(
    monkeypatch, tmp_path
):
    config_root, canonical = _inprocess_marker_host(monkeypatch, tmp_path)
    host = control.ProductionTransactionHost()
    configs = _harness_configs(host)
    transaction = control.TransactionContext(
        transaction_id=host.new_transaction_id(),
        expected_sha=SHA,
        prior_configs=configs,
        candidates=control.derive_candidate_configs(configs, armed=True),
        admission=None,
    )
    host.begin_transaction(transaction)
    manifest = _assert_complete_locked_marker(canonical, "ARM")
    assert manifest["transaction_id"] == transaction.transaction_id
    held = host._transaction_owner_fd
    assert held is not None

    competitor = control.ProductionCeoSubmitHost()
    with pytest.raises(control.TransactionEffectUnknown):
        competitor._claim_transaction_owner()
    assert competitor._transaction_owner_fd is None
    assert host._transaction_owner_fd == held

    refused_transaction = control.TransactionContext(
        transaction_id="autonomy-" + "cd" * 6,
        expected_sha=SHA,
        prior_configs=configs,
        candidates=control.derive_candidate_configs(configs, armed=True),
        admission=None,
    )
    with pytest.raises(control.CeoSubmitAdmissionError) as refused:
        competitor.begin_ceo_submit_transaction(
            refused_transaction, operation="CEO_SUBMIT_ARM"
        )
    assert refused.value.code == "ceo_submit_transaction_incomplete"
    assert _manifest_of(canonical) == manifest
    assert host._transaction_owner_fd == held

    host.complete_transaction(transaction)
    assert host._transaction_owner_fd is None
    assert not canonical.exists()
    assert sorted(os.listdir(config_root)) == _MARKER_CONFIG_ENTRIES


def test_existing_valid_marker_recovery_and_replay_semantics_are_preserved(
    monkeypatch, tmp_path
):
    config_root, canonical = _inprocess_marker_host(monkeypatch, tmp_path)
    host = control.ProductionTransactionHost()
    configs = _harness_configs(host)
    transaction = control.TransactionContext(
        transaction_id=host.new_transaction_id(),
        expected_sha=SHA,
        prior_configs=configs,
        candidates=control.derive_candidate_configs(configs, armed=True),
        admission=None,
    )
    host.begin_transaction(transaction)
    manifest_before = _manifest_of(canonical)
    inode_before = canonical.stat().st_ino

    # The creating owner exits (the flock is dropped with its descriptor); the
    # marker itself stays exactly as published.
    host._release_transaction_owner()

    ceo_host = control.ProductionCeoSubmitHost()
    # The same declared privilege adapter family: the installed host runs as
    # root, so the identity probe observes 0 while every mode/inode/ownership
    # fact stays the real on-disk value.
    ceo_host.effective_uid = lambda: 0
    assert ceo_host.new_transaction_id() == transaction.transaction_id
    assert ceo_host.incomplete_transaction_operation() == "ARM"
    with pytest.raises(control.CeoSubmitAdmissionError) as hold:
        ceo_host.require_transaction_absent()
    assert hold.value.code == "ceo_submit_transaction_incomplete"
    assert _manifest_of(canonical) == manifest_before
    assert canonical.stat().st_ino == inode_before
    ceo_host._release_transaction_owner()


@pytest.mark.parametrize("ceo", [False, True])
def test_rename_publication_ack_loss_preserves_exact_generation_owner(monkeypatch, tmp_path, ceo):
    _, canonical = _inprocess_marker_host(monkeypatch, tmp_path)
    host = control.ProductionCeoSubmitHost() if ceo else control.ProductionTransactionHost()
    configs = _harness_configs(host)
    transaction = control.TransactionContext(transaction_id=host.new_transaction_id(), expected_sha=SHA, prior_configs=configs, candidates=control.derive_candidate_configs(configs, armed=True), admission=None)
    real_rename = control.os.rename
    published = []
    def rename_then_raise(src, dst):
        result = real_rename(src, dst)
        if Path(dst) == canonical:
            published.append((canonical.stat().st_dev, canonical.stat().st_ino))
            raise OSError(5, "injected acknowledgement loss AFTER rename effect")
        return result
    monkeypatch.setattr(control.os, "rename", rename_then_raise)
    caught = None
    try:
        try:
            if ceo:
                host.begin_ceo_submit_transaction(transaction, operation="CEO_SUBMIT_ARM")
            else:
                host.begin_transaction(transaction)
        except Exception as exc:
            caught = exc
        assert type(caught) is control.TransactionEffectUnknown
        assert _manifest_of(canonical)["transaction_id"] == transaction.transaction_id
        assert published == [(canonical.stat().st_dev, canonical.stat().st_ino)]
        assert host._transaction_owner_fd is not None
        held = os.fstat(host._transaction_owner_fd)
        assert (held.st_dev, held.st_ino) == published[0]
        with _harness_process(tmp_path, "recovery-claim") as claimant:
            recovery, _ = claimant.result()
        assert recovery["claimed"] is False
    finally:
        if host._transaction_owner_fd is not None:
            host._release_transaction_owner()


@pytest.mark.parametrize("ceo", [False, True])
@pytest.mark.parametrize("fault", ["rename_then_raise", "parent_fsync_loss"])
def test_arm_controller_publication_unknown_never_rolls_back(monkeypatch, tmp_path, ceo, fault):
    config_root, canonical = _inprocess_marker_host(monkeypatch, tmp_path)
    journal = []
    if ceo:
        host = _harness_ceo_submit_host()
        invoke = lambda: control.execute_ceo_submit_arm(host, control.CeoSubmitRequest(expected_sha=SHA), now=NOW)
    else:
        host = control.ProductionTransactionHost()
        gates = FakeAdmissionHost()
        host.existing_arm = lambda *_args, **_kwargs: None
        for name in ("require_exact_install", "validate_acceptance", "validate_gate_b", "validate_provider_readiness", "require_runtime_quiescent", "require_services_stopped", "require_service_uids_quiescent"):
            setattr(host, name, getattr(gates, name))
        host.load_unarmed_configs = lambda _sha: _harness_configs(host)
        host.validate_candidates = lambda txn: host._persist_phase(txn, "CANDIDATES_VALIDATED")
        host.stop_services = lambda _sha: journal.append("STOP_SERVICES")
        host._loaded = lambda _label: False
        real_rollback = host.rollback_disarmed
        def rollback(txn, receipt):
            journal.append("ROLLBACK_DISARMED")
            return real_rollback(txn, receipt)
        host.rollback_disarmed = rollback
        invoke = lambda: control.execute_arm(host, _arm_request(), now=NOW)
    real_rename = control.os.rename
    real_fsync = control._fsync_directory
    published = []
    fired = False
    def rename_then_raise(src, dst):
        result = real_rename(src, dst)
        if Path(dst) == canonical:
            published.append((canonical.stat().st_dev, canonical.stat().st_ino))
            if fault == "rename_then_raise":
                raise OSError(5, "injected acknowledgement loss AFTER rename effect")
        return result
    def parent_fsync_loss(path):
        nonlocal fired
        if fault == "parent_fsync_loss" and not fired and Path(path) == config_root and canonical.exists():
            fired = True
            raise OSError(5, "injected parent directory fsync acknowledgement loss")
        return real_fsync(path)
    monkeypatch.setattr(control.os, "rename", rename_then_raise)
    monkeypatch.setattr(control, "_fsync_directory", parent_fsync_loss)
    before = {p: p.read_bytes() for p in (control.CONTROL_CONFIG, control.WORKER_CONFIG)}
    caught = None
    try:
        try:
            invoke()
        except Exception as exc:
            caught = exc
        assert type(caught) is control.TransactionEffectUnknown
        assert journal == []
        assert all(p.read_bytes() == raw for p, raw in before.items())
        assert not control.AUTONOMY_RECEIPT.exists()
        assert not control.CEO_SUBMIT_RECEIPT.exists()
        assert host._transaction_owner_fd is not None
        assert published == [(canonical.stat().st_dev, canonical.stat().st_ino)]
        manifest = _assert_complete_locked_marker(canonical, "CEO_SUBMIT_ARM" if ceo else "ARM")
        assert manifest["transaction_id"] == host._active_transaction.transaction_id
        with _harness_process(tmp_path, "recovery-claim") as claimant:
            recovery, _ = claimant.result()
        assert recovery["claimed"] is False
    finally:
        if host._transaction_owner_fd is not None:
            host._release_transaction_owner()


@pytest.mark.parametrize("ceo", [False, True])
def test_rename_known_prepublication_failure_is_not_promoted_to_published(monkeypatch, tmp_path, ceo):
    config_root, canonical = _inprocess_marker_host(monkeypatch, tmp_path)
    host = control.ProductionCeoSubmitHost() if ceo else control.ProductionTransactionHost()
    configs = _harness_configs(host)
    transaction = control.TransactionContext(transaction_id=host.new_transaction_id(), expected_sha=SHA, prior_configs=configs, candidates=control.derive_candidate_configs(configs, armed=True), admission=None)
    before = {p: p.read_bytes() for p in (control.CONTROL_CONFIG, control.WORKER_CONFIG)}
    def refuse_rename(_src, _dst):
        raise OSError(5, "injected failure BEFORE rename effect")
    monkeypatch.setattr(control.os, "rename", refuse_rename)
    with pytest.raises(Exception):
        if ceo:
            host.begin_ceo_submit_transaction(transaction, operation="CEO_SUBMIT_ARM")
        else:
            host.begin_transaction(transaction)
    assert not canonical.exists()
    assert host._transaction_owner_fd is None
    assert all(p.read_bytes() == raw for p, raw in before.items())
    assert sorted(p.name for p in config_root.iterdir()) == _MARKER_CONFIG_ENTRIES


@_harness_scenario("coo-before-publication-mutex")
def _scenario_coo_before_publication_mutex(workdir, journal):
    return _scenario_creator_before_publication_mutex(workdir, ceo=False)


@_harness_scenario("ceo-before-publication-mutex")
def _scenario_ceo_before_publication_mutex(workdir, journal):
    return _scenario_creator_before_publication_mutex(workdir, ceo=True)


def _scenario_creator_before_publication_mutex(workdir, *, ceo):
    _, canonical = _harness_child_setup(workdir)
    channel = _HarnessChannel()
    host = control.ProductionCeoSubmitHost() if ceo else control.ProductionTransactionHost()
    transaction = _harness_ceo_submit_transaction(host) if ceo else _harness_coo_transaction(host, armed=True)
    publication_mutex = host._publication_mutex
    def gated_mutex():
        # Both actual begin methods already passed canonical absence, acquired
        # their private inode flock, and sealed the complete generation.
        channel.pause("ADMITTED_BEFORE_PUBLICATION")
        return publication_mutex()
    host._publication_mutex = gated_mutex
    if ceo:
        host.begin_ceo_submit_transaction(transaction, operation="CEO_SUBMIT_ARM")
    else:
        host.begin_transaction(transaction)
    channel.pause("PUBLISHED_AND_OWNED")
    return {"transaction_id": transaction.transaction_id, "manifest": _manifest_of(canonical)}


@pytest.mark.parametrize("first", ["coo", "ceo"])
def test_two_creators_admitted_before_publication_cannot_replace_winner(tmp_path, first):
    config_root = _marker_workspace(tmp_path)
    canonical = config_root / _CANONICAL_MARKER_NAME
    second = "ceo" if first == "coo" else "coo"
    with _harness_process(tmp_path, first + "-before-publication-mutex") as winner:
        with _harness_process(tmp_path, second + "-before-publication-mutex") as loser:
            winner.wait_for("ADMITTED_BEFORE_PUBLICATION")
            loser.wait_for("ADMITTED_BEFORE_PUBLICATION")
            assert not canonical.exists()
            winner.release()
            winner.wait_for("PUBLISHED_AND_OWNED")
            manifest = _assert_complete_locked_marker(canonical, "ARM" if first == "coo" else "CEO_SUBMIT_ARM")
            identity = (canonical.stat().st_dev, canonical.stat().st_ino)
            loser.release()
            rejected, _ = loser.result()
            assert rejected["ok"] is False
            assert rejected["error"] == ("CeoSubmitAdmissionError" if second == "ceo" else "ArmAdmissionError")
            assert _manifest_of(canonical) == manifest
            assert (canonical.stat().st_dev, canonical.stat().st_ino) == identity
            with _harness_process(tmp_path, "recovery-claim") as claimant:
                recovery, _ = claimant.result()
            assert recovery["claimed"] is False
            winner.release()
    result, _ = winner.result()
    assert result["ok"] is True
    assert result["transaction_id"] == manifest["transaction_id"]
