"""The closed client lifecycle: start-client and stop-client.

Only the exact label com.mastermind.executive.fabric-application-tunnel is ever
addressed. Each phase issues at most one bounded launchctl operation and then
reads back; a pending or unknown outcome requires the original reconciliation
rather than another bootstrap, bootout, kickstart or process kill. The
incumbent OS transport label and the Go lifecycle owner are never touched.
"""
import os

import pytest

from ops.executive_os import application_tunnel_control as control
from tests.test_application_tunnel_control import FakeSystem, harness, sealed_root  # noqa: F401


def _installed(harness):
    harness.stage()
    control.apply_client(paths=harness.paths, system=FakeSystem())
    return harness.server_receipt()


def test_start_client_issues_exactly_one_bounded_command_and_reads_back(harness):
    receipt_path = _installed(harness)
    system = FakeSystem()
    receipt = control.start_client(server_receipt=receipt_path, paths=harness.paths, system=system)
    assert receipt["state"] == "STARTED"
    assert receipt["commands"] == 1
    assert receipt["service_started"] is True
    assert receipt["tunnel_proven"] is False
    assert receipt["application_proven"] is False
    assert receipt["provider_effects_settled"] is False
    assert system.calls == [("bootstrap", str(harness.paths.plist))]


def test_a_second_start_issues_no_second_command(harness):
    receipt_path = _installed(harness)
    launchd = {}
    first = FakeSystem(launchd=launchd)
    control.start_client(server_receipt=receipt_path, paths=harness.paths, system=first)
    second = FakeSystem(launchd=launchd)
    receipt = control.start_client(server_receipt=receipt_path, paths=harness.paths, system=second)
    assert receipt["state"] == "ALREADY_STARTED"
    assert receipt["commands"] == 0
    assert second.calls == []


def test_loaded_label_without_running_pid_cannot_claim_start(harness):
    receipt_path = _installed(harness)
    system = FakeSystem(pid=None)
    with pytest.raises(ValueError, match="outcome is unknown"):
        control.start_client(server_receipt=receipt_path, paths=harness.paths, system=system)
    assert len(system.calls) == 1
    with pytest.raises(ValueError, match="not proven running"):
        control.start_client(server_receipt=receipt_path, paths=harness.paths, system=system)
    assert len(system.calls) == 1


def test_running_pid_must_match_actual_chisel_argv(harness):
    receipt_path = _installed(harness)
    system = FakeSystem()
    system.process_matches = lambda pid, expected: False
    with pytest.raises(ValueError, match="outcome is unknown"):
        control.start_client(server_receipt=receipt_path, paths=harness.paths, system=system)
    assert len(system.calls) == 1


def test_start_verifies_release_again_and_preserves_no_command_on_drift(harness):
    receipt_path = _installed(harness)
    helper = harness.release / "ops/executive_os/os_tunnel_entry.py"
    helper.chmod(0o644)
    helper.write_bytes(helper.read_bytes() + b"\n# unexpected source drift\n")
    helper.chmod(0o444)
    system = FakeSystem()
    with pytest.raises(ValueError, match="release"):
        control.start_client(server_receipt=receipt_path, paths=harness.paths, system=system)
    assert system.calls == []


def test_historical_started_receipt_cannot_claim_current_running_or_restart(harness):
    receipt_path = _installed(harness)
    system = FakeSystem()
    control.start_client(server_receipt=receipt_path, paths=harness.paths, system=system)
    absent = FakeSystem()
    assert control.reconcile(paths=harness.paths, system=absent)["service_state"] == "UNKNOWN"
    with pytest.raises(ValueError, match="original start outcome"):
        control.start_client(server_receipt=receipt_path, paths=harness.paths, system=absent)
    assert absent.calls == []


def test_stop_reconciliation_uses_latest_stop_and_actual_absence(harness):
    receipt_path = _installed(harness)
    system = FakeSystem()
    control.start_client(server_receipt=receipt_path, paths=harness.paths, system=system)
    control.stop_client(paths=harness.paths, system=system)
    assert control.reconcile(paths=harness.paths, system=system)["service_state"] == "STOPPED"


def test_stop_refuses_wrong_live_process_and_does_not_claim_orphan_absence(harness):
    receipt_path = _installed(harness)
    system = FakeSystem()
    control.start_client(server_receipt=receipt_path, paths=harness.paths, system=system)
    system.process_matches = lambda pid, expected: False
    with pytest.raises(ValueError, match="process identity is unproven"):
        control.stop_client(paths=harness.paths, system=system)
    assert not any(kind == "bootout" for kind, _ in system.calls)
    binary = harness.paths.executive_root / "transports/chisel" / ("b" * 64) / "chisel"
    orphan = FakeSystem(processes=[{"pid": 9900, "argv": [str(binary), "client", control.REVERSE_TARGET]}])
    with pytest.raises(ValueError, match="unowned application process"):
        control.stop_client(paths=harness.paths, system=orphan)
    assert orphan.calls == []


def test_native_command_path_with_spaces_still_blocks_duplicate_or_orphan(harness):
    receipt_path = _installed(harness)
    command = "/Library/Application Support/MastermindExecutive/transports/chisel/" + "b" * 64 + "/chisel client " + control.REVERSE_TARGET
    system = FakeSystem(processes=[{"pid": 9900, "command": command}])
    with pytest.raises(ValueError, match="concurrent same-purpose"):
        control.start_client(server_receipt=receipt_path, paths=harness.paths, system=system)
    with pytest.raises(ValueError, match="unowned application process"):
        control.stop_client(paths=harness.paths, system=system)
    assert system.calls == []


@pytest.mark.parametrize("phase", ["start", "stop"])
def test_reconcile_cannot_settle_corrupt_or_foreign_lifecycle_intent(harness, phase):
    receipt_path = _installed(harness)
    system = FakeSystem()
    control.start_client(server_receipt=receipt_path, paths=harness.paths, system=system)
    if phase == "stop":
        control.stop_client(paths=harness.paths, system=system)
    target = harness.paths.operation_root / ("stage/operation/%s-intent.json" % phase)
    value = control.decode(target.read_bytes())
    value["stage_digest"] = "0" * 64
    target.write_bytes(control.canonical(value))
    with pytest.raises(ValueError, match="lifecycle intent differs"):
        control.reconcile(paths=harness.paths, system=system)


def test_a_foreign_launchd_label_is_refused_without_any_command(harness):
    receipt_path = _installed(harness)
    system = FakeSystem(launchd={control.LABEL: (True, {"arguments": ["/bin/sh", "-c", "sleep 1"],
                                                        "pid": 99})})
    with pytest.raises(ValueError) as error:
        control.start_client(server_receipt=receipt_path, paths=harness.paths, system=system)
    assert "foreign launchd label" in str(error.value)
    assert system.calls == []


def test_a_concurrent_same_purpose_client_is_refused(harness):
    receipt_path = _installed(harness)
    binary = harness.paths.executive_root / "transports" / "chisel" / ("b" * 64) / "chisel"
    system = FakeSystem(processes=[{"pid": 4242, "argv": [str(binary), "client",
                                                           "R:127.0.0.1:50142:127.0.0.1:4142"]}])
    with pytest.raises(ValueError) as error:
        control.start_client(server_receipt=receipt_path, paths=harness.paths, system=system)
    assert "concurrent same-purpose client" in str(error.value)
    assert system.calls == []


def test_a_stale_start_intent_without_a_receipt_requires_reconciliation(harness):
    receipt_path = _installed(harness)
    journal = harness.paths.operation_root / "stage" / "operation"
    journal.mkdir(exist_ok=True)
    (journal / "start-intent.json").write_bytes(control.canonical({
        "schema": control.SCHEMA, "phase": "start-client",
        "operation_id": control.operation_identity()}))
    system = FakeSystem()
    with pytest.raises(ValueError) as error:
        control.start_client(server_receipt=receipt_path, paths=harness.paths, system=system)
    assert "original start outcome is unknown" in str(error.value)
    assert system.calls == []


def test_start_client_refuses_without_the_server_grant(harness):
    harness.stage()
    control.apply_client(paths=harness.paths, system=FakeSystem())
    system = FakeSystem()
    with pytest.raises(ValueError) as error:
        control.start_client(server_receipt=None, paths=harness.paths, system=system)
    assert "server grant is not applied" in str(error.value)
    assert system.calls == []


def test_start_client_refuses_a_client_binary_that_drifted(harness):
    receipt_path = _installed(harness)
    system = FakeSystem(client_sha="d" * 64)
    with pytest.raises(ValueError) as error:
        control.start_client(server_receipt=receipt_path, paths=harness.paths, system=system)
    assert "client binary digest differs" in str(error.value)
    assert system.calls == []


def test_start_client_refuses_when_the_client_is_not_installed(harness):
    harness.stage()
    receipt_path = harness.server_receipt()
    system = FakeSystem()
    with pytest.raises(ValueError) as error:
        control.start_client(server_receipt=receipt_path, paths=harness.paths, system=system)
    assert "application client is not installed" in str(error.value)
    assert system.calls == []


def test_stop_client_issues_exactly_one_bounded_command(harness):
    receipt_path = _installed(harness)
    launchd = {}
    system = FakeSystem(launchd=launchd)
    control.start_client(server_receipt=receipt_path, paths=harness.paths, system=system)
    stopper = FakeSystem(launchd=launchd)
    receipt = control.stop_client(paths=harness.paths, system=stopper)
    assert receipt["state"] == "STOPPED"
    assert receipt["commands"] == 1
    assert receipt["service_started"] is False
    assert receipt["provider_effects_settled"] is False
    assert stopper.calls == [("bootout", control.LABEL)]


def test_a_stop_of_an_absent_service_issues_no_command(harness):
    _installed(harness)
    system = FakeSystem()
    receipt = control.stop_client(paths=harness.paths, system=system)
    assert receipt["state"] == "ALREADY_STOPPED"
    assert receipt["commands"] == 0
    assert system.calls == []


def test_a_refused_stop_is_never_retried(harness):
    receipt_path = _installed(harness)
    launchd = {}
    system = FakeSystem(launchd=launchd)
    control.start_client(server_receipt=receipt_path, paths=harness.paths, system=system)
    stopper = FakeSystem(launchd=launchd, bootout_returncode=1)
    with pytest.raises(ValueError) as error:
        control.stop_client(paths=harness.paths, system=stopper)
    assert "stop command was refused" in str(error.value)
    assert stopper.calls == [("bootout", control.LABEL)]
    again = FakeSystem(launchd=launchd, bootout_returncode=1)
    with pytest.raises(ValueError) as error:
        control.stop_client(paths=harness.paths, system=again)
    assert "original stop outcome requires reconciliation" in str(error.value)
    assert again.calls == []


def test_a_refused_start_is_never_retried(harness):
    receipt_path = _installed(harness)
    system = FakeSystem(bootstrap_returncode=1)
    with pytest.raises(ValueError) as error:
        control.start_client(server_receipt=receipt_path, paths=harness.paths, system=system)
    assert "start command was refused" in str(error.value)
    assert system.calls == [("bootstrap", str(harness.paths.plist))]
    again = FakeSystem(bootstrap_returncode=1)
    with pytest.raises(ValueError) as error:
        control.start_client(server_receipt=receipt_path, paths=harness.paths, system=again)
    assert "original start outcome requires reconciliation" in str(error.value)
    assert again.calls == []


def test_an_unknown_start_outcome_is_never_retried(harness):
    receipt_path = _installed(harness)
    system = FakeSystem(autoload=False)
    with pytest.raises(ValueError) as error:
        control.start_client(server_receipt=receipt_path, paths=harness.paths, system=system)
    assert "start command outcome is unknown" in str(error.value)
    assert system.calls == [("bootstrap", str(harness.paths.plist))]
    again = FakeSystem()
    with pytest.raises(ValueError) as error:
        control.start_client(server_receipt=receipt_path, paths=harness.paths, system=again)
    assert "original start outcome requires reconciliation" in str(error.value)
    assert again.calls == []


def test_a_lost_acknowledgement_is_recovered_by_readback_not_by_a_second_command(harness):
    receipt_path = _installed(harness)
    launchd = {}
    system = FakeSystem(launchd=launchd)
    control.start_client(server_receipt=receipt_path, paths=harness.paths, system=system)
    journal = harness.paths.operation_root / "stage" / "operation"
    (journal / "start-receipt.json").unlink()
    state = control.reconcile(paths=harness.paths, system=system)
    assert state["service_state"] == "STARTED"
    assert state["settled"]["settled_by"] == "launchd_state"
    again = FakeSystem(launchd=launchd)
    receipt = control.start_client(server_receipt=receipt_path, paths=harness.paths, system=again)
    assert receipt["state"] == "ALREADY_STARTED"
    assert again.calls == []


def test_reconcile_reports_an_unsettled_start_outcome(harness):
    receipt_path = _installed(harness)
    system = FakeSystem()
    control.start_client(server_receipt=receipt_path, paths=harness.paths, system=system)
    journal = harness.paths.operation_root / "stage" / "operation"
    (journal / "start-receipt.json").unlink()
    absent = FakeSystem()
    state = control.reconcile(paths=harness.paths, system=absent)
    assert state["service_state"] == "UNKNOWN"
    assert state["settled"]["settled_by"] == "launchd_state_absence"


def test_the_incumbent_os_transport_label_and_the_go_owner_are_never_touched(harness):
    receipt_path = _installed(harness)
    system = FakeSystem()
    control.start_client(server_receipt=receipt_path, paths=harness.paths, system=system)
    control.stop_client(paths=harness.paths, system=system)
    for kind, target in system.calls:
        assert kind in ("bootstrap", "bootout")
        assert "os-public-tunnel" not in target
        assert "go-shim" not in target
        assert "go_ctl" not in target
        assert "4142" not in target
    assert control.LABEL not in ("com.mastermind.executive.os-public-tunnel",
                                 "com.mastermind.go-shim-runtime")


def test_the_plist_carries_no_credential_and_no_inherited_environment(harness):
    _installed(harness)
    plist = harness.paths.plist.read_text()
    assert "application-tunnel.auth" not in plist
    assert "AUTH" not in plist
    assert "mastermind-fabric-app" not in plist
    assert "-I" in plist and "-B" in plist
    assert "<key>UserName</key>" in plist
    assert "root" in plist


def test_concurrent_operations_contend_on_the_same_purpose_custody(harness):
    import fcntl
    harness.stage()
    lock = harness.paths.operation_root / "purpose.lock"
    descriptor = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError) as error:
            control.reconcile(paths=harness.paths, system=FakeSystem())
        assert "purpose custody is busy" in str(error.value)
    finally:
        os.close(descriptor)
