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
    assert "credential_rotation_interlock.py" in install


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
