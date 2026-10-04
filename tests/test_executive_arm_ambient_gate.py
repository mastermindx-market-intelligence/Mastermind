"""Production arm admission reuses exact ambient identity without signaling."""
from dataclasses import replace
from types import SimpleNamespace
import inspect
import signal

import pytest

from control_plane import executive_ambient_process as ambient
from control_plane import executive_worker_broker as broker
from ops.executive_os import autonomy_control as control


IDENTITY = ambient.AmbientProcessIdentity(
    pid=123, uid=451, launchd_domain="user/451",
    launchd_label=ambient.AMBIENT_LAUNCHD_LABEL, launchd_reported_pid=123,
    plist_path=ambient.AMBIENT_PLIST_PATH, program_path=ambient.AMBIENT_PROGRAM_PATH,
    executable_path=ambient.AMBIENT_PROGRAM_PATH, executable_device=1,
    executable_inode=2, codesign_identifier=ambient.AMBIENT_CODESIGN_IDENTIFIER,
    codesign_verified=True,
)
ATTESTED = ambient.AmbientClassification("attested", (IDENTITY,))


def setup(monkeypatch, *, control_pids=(), worker_pids=(123,), classification=ATTESTED):
    calls = []
    monkeypatch.setattr(control.pwd, "getpwnam", lambda name: SimpleNamespace(
        pw_uid=450 if name == control.CONTROL_USER else 451))
    def processes(uid):
        calls.append(("processes", uid))
        return control_pids if uid == 450 else worker_pids
    def classify(*, worker_uid):
        calls.append(("classify", worker_uid))
        if isinstance(classification, Exception):
            raise classification
        return classification
    monkeypatch.setattr(broker, "_ps_pids_for_uid", processes)
    monkeypatch.setattr(ambient, "DarwinDistnotedClassifier",
                        lambda: SimpleNamespace(classify=classify))
    return control.ProductionArmHost(), calls


def refused(host, code):
    with pytest.raises(control.ArmAdmissionError) as error:
        host.require_service_uids_quiescent()
    assert error.value.code == code


def test_empty_service_principals_need_no_ambient_exception(monkeypatch):
    host, calls = setup(monkeypatch, worker_pids=())
    host.require_service_uids_quiescent()
    assert calls == [("processes", 450), ("processes", 451)]


def test_only_exact_worker_ambient_passes_and_is_observed_again(monkeypatch):
    host, calls = setup(monkeypatch)
    host.require_service_uids_quiescent()
    assert calls == [("processes", 450), ("processes", 451), ("classify", 451),
                     ("processes", 451), ("classify", 451)]
    host.require_service_uids_quiescent()
    assert len(calls) == 10


@pytest.mark.parametrize("worker", [(123, 456), (456,), (0,), (-1,)])
def test_any_residual_from_broad_uid_owner_refuses(monkeypatch, worker):
    host, _ = setup(monkeypatch, worker_pids=worker)
    refused(host, "service_uid_process_live")


def test_control_has_no_new_ambient_exception(monkeypatch):
    host, calls = setup(monkeypatch, control_pids=(123,))
    refused(host, "service_uid_process_live")
    assert calls == [("processes", 450)]


@pytest.mark.parametrize("classification,code", [
    (ambient.AmbientClassification("absent"), "service_uid_process_live"),
    (ambient.AmbientClassification("failed_closed"), "service_uid_process_unknown"),
    (OSError("unavailable"), "service_uid_process_unknown"),
    (SimpleNamespace(status="attested", identities=(IDENTITY,)), "service_uid_process_unknown"),
    (ambient.AmbientClassification("attested", (replace(IDENTITY, uid=452),)), "service_uid_process_live"),
    (ambient.AmbientClassification("attested", (replace(IDENTITY, launchd_reported_pid=456),)), "service_uid_process_live"),
    (ambient.AmbientClassification("attested", (replace(IDENTITY, codesign_verified=False),)), "service_uid_process_unknown"),
    (ambient.AmbientClassification("attested", (IDENTITY, IDENTITY)), "service_uid_process_live"),
])
def test_absent_unknown_forged_or_mismatched_attribution_refuses(monkeypatch, classification, code):
    host, _ = setup(monkeypatch, classification=classification)
    refused(host, code)


def test_process_table_failure_refuses(monkeypatch):
    host, _ = setup(monkeypatch)
    def unavailable(_uid):
        raise broker.DedicatedUIDError("unavailable")
    monkeypatch.setattr(broker, "_ps_pids_for_uid", unavailable)
    refused(host, "service_uid_process_unknown")


def test_process_created_during_attestation_refuses(monkeypatch):
    host, _ = setup(monkeypatch)
    values = iter([(), (123,), (123, 456)])
    monkeypatch.setattr(broker, "_ps_pids_for_uid", lambda _uid: next(values))
    refused(host, "service_uid_process_unknown")


def test_attribution_changes_during_second_observation_refuses(monkeypatch):
    host, _ = setup(monkeypatch)
    values = iter([ATTESTED, ambient.AmbientClassification("absent")])
    monkeypatch.setattr(ambient, "DarwinDistnotedClassifier",
                        lambda: SimpleNamespace(classify=lambda **_kwargs: next(values)))
    refused(host, "service_uid_process_unknown")


def test_gate_has_no_process_mutation_or_credential_path():
    source = inspect.getsource(control.ProductionArmHost.require_service_uids_quiescent)
    for forbidden in ("DedicatedUIDSweeper(", ".kill(", "os.kill", "bootout", "kickstart",
                      "subprocess.run", "auth.json", "receipt_path"):
        assert forbidden not in source


def test_worker_account_must_match_canonical_slot_uid(monkeypatch):
    host, calls = setup(monkeypatch)
    monkeypatch.setattr(control.pwd, 'getpwnam', lambda name: SimpleNamespace(
        pw_uid=450 if name == control.CONTROL_USER else 999))
    refused(host, 'service_uid_process_unknown')
    assert calls == []


def test_control_uid_quiesce_signals_only_fixed_control_principal(monkeypatch):
    state = {450: [101, 102], 451: [123]}
    calls = []
    monkeypatch.setattr(
        control.pwd, "getpwnam",
        lambda name: SimpleNamespace(pw_uid=450 if name == control.CONTROL_USER else 451),
    )

    def processes(uid):
        calls.append(("processes", uid))
        return tuple(state[uid])

    def kill(pid, signum):
        calls.append(("kill", pid, signum))
        assert pid in state[450]
        assert pid not in state[451]
        state[450].remove(pid)

    monkeypatch.setattr(broker, "_ps_pids_for_uid", processes)
    monkeypatch.setattr(control.os, "kill", kill)
    monkeypatch.setattr(control.time, "sleep", lambda _seconds: None)

    signalled = control.ProductionArmHost().quiesce_control_uid_for_arm()

    assert signalled == (101, 102)
    assert state == {450: [], 451: [123]}
    assert not any(call[:2] == ("processes", 451) for call in calls)
    assert [(pid, signum) for kind, pid, signum in calls if kind == "kill"] == [
        (101, signal.SIGTERM),
        (102, signal.SIGTERM),
    ]


def test_control_uid_quiesce_is_read_only_replay_when_already_empty(monkeypatch):
    killed = []
    monkeypatch.setattr(
        control.pwd, "getpwnam", lambda _name: SimpleNamespace(pw_uid=450)
    )
    monkeypatch.setattr(broker, "_ps_pids_for_uid", lambda uid: ())
    monkeypatch.setattr(control.os, "kill", lambda pid, signum: killed.append((pid, signum)))

    assert control.ProductionArmHost().quiesce_control_uid_for_arm() == ()
    assert killed == []


def test_control_uid_quiesce_escalates_to_sigkill_and_proves_absence(monkeypatch):
    live = [321]
    signals = []
    monkeypatch.setattr(
        control.pwd, "getpwnam", lambda _name: SimpleNamespace(pw_uid=450)
    )
    monkeypatch.setattr(broker, "_ps_pids_for_uid", lambda uid: tuple(live))

    def kill(pid, signum):
        signals.append(signum)
        if signum == signal.SIGKILL:
            live.clear()

    monkeypatch.setattr(control.os, "kill", kill)
    monkeypatch.setattr(control.time, "sleep", lambda _seconds: None)

    signalled = control.ProductionArmHost().quiesce_control_uid_for_arm()

    assert signalled == (321,)
    assert signal.SIGTERM in signals
    assert signal.SIGKILL in signals
    assert live == []


def test_control_uid_quiesce_refuses_if_process_survives_both_signals(monkeypatch):
    monkeypatch.setattr(
        control.pwd, "getpwnam", lambda _name: SimpleNamespace(pw_uid=450)
    )
    monkeypatch.setattr(broker, "_ps_pids_for_uid", lambda uid: (456,))
    monkeypatch.setattr(control.os, "kill", lambda _pid, _signum: None)
    monkeypatch.setattr(control.time, "sleep", lambda _seconds: None)

    with pytest.raises(control.ArmAdmissionError) as error:
        control.ProductionArmHost().quiesce_control_uid_for_arm()

    assert error.value.code == "service_uid_process_live"


def test_control_uid_quiesce_refuses_invalid_process_identity(monkeypatch):
    monkeypatch.setattr(
        control.pwd, "getpwnam", lambda _name: SimpleNamespace(pw_uid=450)
    )
    monkeypatch.setattr(broker, "_ps_pids_for_uid", lambda uid: (0,))

    with pytest.raises(control.ArmAdmissionError) as error:
        control.ProductionArmHost().quiesce_control_uid_for_arm()

    assert error.value.code == "service_uid_process_unknown"


def test_control_uid_quiesce_cli_has_no_selectable_target_or_signal():
    parser = control._parser()
    sha = "a" * 40
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "arm-quiesce-control-uid",
                "--expected-sha",
                sha,
                "--uid",
                "450",
            ]
        )
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "arm-quiesce-control-uid",
                "--expected-sha",
                sha,
                "--signal",
                "KILL",
            ]
        )
