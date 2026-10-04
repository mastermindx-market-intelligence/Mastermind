"""Acceptance injects canonical owner loss only after observing both replacements."""
from types import SimpleNamespace

import pytest

from ops.executive_os import acceptance


def _fixture(monkeypatch):
    runner = object.__new__(acceptance.Acceptance)
    runner.control_identity = SimpleNamespace(pw_uid=450)
    runner.control_group = SimpleNamespace(gr_gid=450)
    runner.worker_identity = SimpleNamespace(pw_uid=451)
    runner.worker_group = SimpleNamespace(gr_gid=451)
    events = []
    sweep = {
        "schema_version": "mastermind.executive_uid_sweep/v2",
        "observed_at": "2026-08-11T00:00:01+00:00",
        "reason": "broker_startup", "worker_uid": 451, "broker_pid": 202,
        "residual_pids_before": [303], "residual_pids_after": [],
        "signal_name": "SIGKILL", "signal_sent": True,
        "quiescent_observations": 2, "ambient_pids": [],
        "ambient_identities": [], "ambient_attribution": "absent",
        "passed": True, "found_residuals": True,
    }
    broker = dict(adapter_id="codex-cli", broker_pid=202, worker_uid=451,
                  active_run_id=None, active_operator_attempt_id=None,
                  active_operator_generation_id=None, starting=False,
                  validation_busy=False, status_sweep_busy=False,
                  quarantined_reason=None, startup_sweep=sweep)
    pending = dict(service_state="AWAITING_CANARY", startup_reconciliation=[])
    monkeypatch.setattr(acceptance, "_run",
        lambda argv, **kw: events.append(("kill", argv[-1])))
    def worker(label, *, different_from=None):
        assert label == acceptance.WORKER_LABEL and different_from == 102
        events.append(("worker", different_from))
        return 202
    def control(*, different_from=None):
        assert different_from == 101
        events.append(("control", different_from))
        return 201
    def status(command, **kw):
        assert command == "status"
        events.append(("pending",))
        return {"result": pending}
    def broker_status(pid):
        assert pid == 202
        events.append(("broker", pid))
        return broker
    runner._wait_pid = worker
    runner._wait_control = control
    runner._control_request = status
    runner._wait_replacement_broker = broker_status
    runner._assert_process_principal = lambda pid, uid, gid, label: events.append(
        ("principal", pid, uid, gid))
    runner._pid_exists = lambda pid: False
    runner._write_json = lambda name, value: events.append(("persist", name))
    runner._activate_live_canary = lambda c, w: events.append(("activate", c, w))
    return runner, broker, pending, events


def test_interruption_kills_control_then_worker_and_observes_before_activation(monkeypatch):
    runner, broker, pending, events = _fixture(monkeypatch)
    result = runner._restart_interrupted_owners(
        101, 102, 303, "2026-08-11T00:00:00+00:00")
    assert result == (201, 202, broker["startup_sweep"])
    assert events == [
        ("kill", "system/" + acceptance.CONTROL_LABEL),
        ("kill", "system/" + acceptance.WORKER_LABEL),
        ("worker", 102), ("control", 101), ("pending",),
        ("principal", 201, 450, 450), ("principal", 202, 451, 451),
        ("broker", 202),
        ("persist", "interrupted-preactivation-broker-status.json"),
        ("activate", 201, 202),
    ]


@pytest.mark.parametrize("path,value", [
    ("broker_pid", 102), ("worker_uid", 452), ("adapter_id", "claude-code"),
    ("active_run_id", "other"), ("active_operator_attempt_id", "other"),
    ("active_operator_generation_id", "other"), ("starting", True),
    ("validation_busy", True), ("status_sweep_busy", True),
    ("quarantined_reason", "uncertain"),
    ("startup_sweep.worker_uid", 452), ("startup_sweep.broker_pid", 102),
    ("startup_sweep.reason", "run_terminal"),
    ("startup_sweep.residual_pids_before", []),
    ("startup_sweep.residual_pids_after", [303]),
    ("startup_sweep.passed", False),
    ("startup_sweep.observed_at", "2026-08-11T00:00:00+00:00"),
    ("startup_sweep.observed_at", "2026-08-11T00:00:01"),
    ("startup_sweep.observed_at", "invalid"),
])
def test_interruption_refuses_foreign_or_incomplete_startup(monkeypatch, path, value):
    runner, broker, pending, events = _fixture(monkeypatch)
    target = broker
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value
    with pytest.raises(acceptance.AcceptanceError):
        runner._restart_interrupted_owners(101, 102, 303, "2026-08-11T00:00:00+00:00")
    assert not any(e[0] in {"activate", "persist"} for e in events)


@pytest.mark.parametrize("pending", [
    {"service_state": "READY", "startup_reconciliation": []},
    {"service_state": "AWAITING_CANARY", "startup_reconciliation": [{}]},
    {"service_state": "AWAITING_CANARY"},
])
def test_interruption_refuses_early_reconciliation(monkeypatch, pending):
    runner, broker, original, events = _fixture(monkeypatch)
    original.clear()
    original.update(pending)
    with pytest.raises(acceptance.AcceptanceError, match="before canary"):
        runner._restart_interrupted_owners(101, 102, 303, "2026-08-11T00:00:00+00:00")
    assert not any(e[0] in {"broker", "activate", "persist"} for e in events)


def test_interruption_refuses_helper_surviving_startup(monkeypatch):
    runner, broker, pending, events = _fixture(monkeypatch)
    runner._pid_exists = lambda pid: True
    with pytest.raises(acceptance.AcceptanceError, match="helper alive"):
        runner._restart_interrupted_owners(101, 102, 303, "2026-08-11T00:00:00+00:00")
    assert not any(e[0] in {"activate", "persist"} for e in events)


def test_replacement_broker_waits_for_socket_and_exact_pid(monkeypatch):
    runner = object.__new__(acceptance.Acceptance)
    responses = [acceptance.AcceptanceError("not ready"), {"broker_pid": 102},
                 {"broker_pid": 202}]
    calls = []
    def status():
        calls.append("status")
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result
    runner._broker_status = status
    monkeypatch.setattr(acceptance.time, "sleep", lambda seconds: None)
    assert runner._wait_replacement_broker(202) == {"broker_pid": 202}
    assert calls == ["status"] * 3


@pytest.mark.parametrize("fault", [
    None, "outcome_status", "process_was_live", "uid", "pid", "reason",
    "failed", "startup_changed", "stale", "naive",
])
def test_persisted_owner_loss_proof_binds_outcome_and_same_startup(monkeypatch, fault):
    from copy import deepcopy

    runner, broker, pending, events = _fixture(monkeypatch)
    startup = broker["startup_sweep"]
    sweep = deepcopy(startup)
    sweep.update(reason="status_absence", observed_at="2026-08-11T00:00:02+00:00",
                 residual_pids_before=[], signal_sent=False, found_residuals=False,
                 preceding_broker_startup_sweep=deepcopy(startup))
    outcome = dict(status="MISSING_LOST", process_was_live=False)
    if fault == "outcome_status":
        outcome["status"] = "TERMINAL_RECOVERED"
    elif fault == "process_was_live":
        outcome["process_was_live"] = True
    elif fault == "uid":
        sweep["worker_uid"] = 452
    elif fault == "pid":
        sweep["broker_pid"] = 102
    elif fault == "reason":
        sweep["reason"] = "run_terminal"
    elif fault == "failed":
        sweep["passed"] = False
    elif fault == "startup_changed":
        sweep["preceding_broker_startup_sweep"]["observed_at"] = "2026-08-11T00:00:01.1+00:00"
    elif fault == "stale":
        sweep["observed_at"] = "2026-08-11T00:00:00+00:00"
    elif fault == "naive":
        sweep["observed_at"] = "2026-08-11T00:00:02"
    evidence = dict(schema_version="mastermind.executive_reconciliation_evidence/v1",
                    outcome={**outcome, "uid_sweep_receipt_path": None}, uid_sweep=sweep)
    if fault is None:
        runner._assert_owner_loss_reconciliation(outcome, evidence, startup, 202)
    else:
        with pytest.raises(acceptance.AcceptanceError):
            runner._assert_owner_loss_reconciliation(outcome, evidence, startup, 202)


@pytest.mark.parametrize("field,value", [
    ("schema_version", "wrong"), ("attempt_id", "other"), ("job_id", "other"),
    ("status", "TERMINAL_RECOVERED"), ("process_was_live", True),
    ("requeued", True), ("assignment_seal_receipt_path", "/other"),
    ("uid_sweep_receipt_path", "/copied"),
])
def test_durable_reconciliation_envelope_must_match_live_outcome(monkeypatch, field, value):
    from copy import deepcopy

    runner, broker, pending, events = _fixture(monkeypatch)
    startup = broker["startup_sweep"]
    sweep = deepcopy(startup)
    sweep.update(reason="status_absence", observed_at="2026-08-11T00:00:02+00:00",
                 residual_pids_before=[], signal_sent=False, found_residuals=False,
                 preceding_broker_startup_sweep=deepcopy(startup))
    outcome = dict(attempt_id="ATT-proof", job_id="JOB-proof", status="MISSING_LOST",
                   process_was_live=False, requeued=False,
                   assignment_seal_receipt_path="/exact/seal",
                   uid_sweep_receipt_path="/exact/reconcile", error=None)
    evidence = dict(schema_version="mastermind.executive_reconciliation_evidence/v1",
                    outcome={**outcome, "uid_sweep_receipt_path": None}, uid_sweep=sweep)
    runner._assert_owner_loss_reconciliation(outcome, evidence, startup, 202)
    if field == "schema_version":
        evidence[field] = value
    else:
        evidence["outcome"][field] = value
    with pytest.raises(acceptance.AcceptanceError, match="outcome differs"):
        runner._assert_owner_loss_reconciliation(outcome, evidence, startup, 202)


@pytest.mark.parametrize("fault", [
    None, "job_id", "lost_attempt_id", "worker_id", "quota_class", "status",
    "schema_version", "snapshot", "fence",
])
def test_requeued_capacity_receipt_requires_exact_lost_identity(fault):
    runner = object.__new__(acceptance.Acceptance)
    lost = dict(attempt_id="ATT-lost", worker_id="codex-01", quota_class="codex-native",
                fence_generation=3)
    receipt = dict(schema_version="mastermind.executive_proof_capacity_recovery/v1",
                   job_id="JOB-2", lost_attempt_id="ATT-lost", worker_id="codex-01",
                   quota_class="codex-native", status="AVAILABLE",
                   previous_snapshot={"fence_generation": 3})
    if fault == "snapshot":
        receipt["previous_snapshot"] = []
    elif fault == "fence":
        receipt["previous_snapshot"]["fence_generation"] = 2
    elif fault:
        receipt[fault] = "foreign"
    calls = []
    def request(command, *values, persist=None):
        calls.append((command, values, persist))
        return {"result": receipt}
    runner._control_request = request
    if fault:
        with pytest.raises(acceptance.AcceptanceError, match="recovery receipt"):
            runner._recover_requeued_proof_capacity("JOB-2", lost)
    else:
        runner._recover_requeued_proof_capacity("JOB-2", lost)
    assert calls == [("recover-proof-capacity", ("JOB-2", "ATT-lost"),
                      "requeued-capacity-recovery.json")]
