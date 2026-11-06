"""Parent verification of fixed maintenance transitions; all native leaves inert.

The pending Fabric artifact retains its own run and filename. These tests
qualify the assigning parent's release decision without adopting that result.
"""
from types import SimpleNamespace as S
from unittest.mock import Mock

import pytest

from control_plane import executive_incident_maintenance as m
from scripts import executive_os_incident_maintenance as entry
from tests.test_incident_maintenance_config_join import configuration_world
from tests.test_launchctl_disabled_native_format import NATIVE

SOURCE = {"release_sha": "a" * 40, "manifest_sha256": "b" * 64}


@pytest.fixture
def world(monkeypatch):
    configs, _ = configuration_world(monkeypatch)
    state = S(broker="LOADED_IDLE", consumer="UNLOADED", other_owner=False,
              commands=[], observations=0, content_drift_at=None, handles=[],
              cleanup=[], disable_reply=(0, b"", b""), bootout_reply=(0, b"", b""),
              source_calls=0, source_drift=False, disabled=True, absent_reply=True)
    monkeypatch.setattr(m, "sys", S(platform="darwin"))
    monkeypatch.setattr(m, "os", S(geteuid=lambda: 0))
    monkeypatch.setattr(m.host, "sys", S(platform="darwin"))
    monkeypatch.setattr(m.host, "os", S(geteuid=lambda: 0))
    monkeypatch.setattr(m.release.subprocess, "Popen", Mock(side_effect=AssertionError("no native process")))

    def source():
        state.source_calls += 1
        return dict(SOURCE, release_sha="c" * 40) if state.source_drift and state.source_calls > 1 else dict(SOURCE)

    def observe(*, deadline_monotonic_ns):
        state.observations += 1
        from dataclasses import replace
        from tests.incident_release_fixtures import make_observation
        result = make_observation(source=SOURCE, boot="same-boot", states={
            "broker": state.broker, "control": state.consumer,
            "worker": state.consumer})
        rows = []
        for i, row in enumerate(result.roles):
            content = replace(row.content,
                configuration_digest=configs.roles[i].content.configuration_digest if i < 2 else "d" * 64,
                plist_digest="e" * 64 if state.content_drift_at == state.observations else "f" * 64)
            rows.append(replace(row, content=content,
                service_generation_digest=m.release._digest(m.release._CONTENT_DOMAIN, __import__('dataclasses').asdict(content))))
        rows = tuple(rows)
        return replace(result, roles=rows, cohort_content_sha256=m.incident_release._cohort_digest(rows))


    def census(budget):
        return S(observer="own", matching_runtime_instances=("own", "other") if state.other_owner else ("own",))

    def modify(argv, budget):
        state.commands.append(argv)
        reply = state.disable_reply if argv == m._DISABLE else state.bootout_reply
        if isinstance(reply, BaseException):
            raise reply
        if argv == m._BOOTOUT and reply == (0, b"", b""):
            state.broker = "UNLOADED"
        return reply

    def read(argv, budget):
        if argv == m.release._PRINT_DISABLED_ARGV:
            return (0, NATIVE if state.disabled else NATIVE.replace(b"=> disabled", b"=> enabled"), b"")
        assert argv == ("/bin/launchctl", "print", m._SERVICE)
        if not state.absent_reply:
            return 1, b"", b"permission denied\n"
        assert state.broker == "UNLOADED"
        return 113, b"", b'Bad request.\nCould not find service "com.mastermind.executive.privileged" in domain for system\n'

    def acquire(*, deadline_monotonic_ns):
        handle = S(boot="same-boot", owner="own")
        state.handles.append(handle)
        return handle

    def release(handle):
        assert handle in state.handles and handle not in state.cleanup
        state.cleanup.append(handle)

    monkeypatch.setattr(m, "_source", source)
    monkeypatch.setattr(m.incident_release, "_observe_incident_release", observe)
    monkeypatch.setattr(m.host, "_root_census", census)
    monkeypatch.setattr(m.origin, "_run_owned_native_command", modify)
    monkeypatch.setattr(m.release, "_command", read)
    monkeypatch.setattr(m.namespace, "_acquire_namespace", acquire)
    monkeypatch.setattr(m.namespace, "_release_namespace", release)
    monkeypatch.setattr(m.namespace, "_require_socket_absent", Mock())
    monkeypatch.setattr(m.host, "_observe_old_owner_exclusion", Mock(
        return_value=S(boot_id="same-boot", census=S(observer="own"))))
    monkeypatch.setattr(m.retirement, "_candidate", Mock(return_value=None))
    monkeypatch.setattr(m.retirement, "_require_retained_absent", Mock())
    return state


@pytest.mark.parametrize("initial,expected", [("LOADED_IDLE", 2), ("UNLOADED", 0)])
def test_success_uses_only_fixed_once_verbs_and_releases_own_handles(world, initial, expected):
    world.broker = initial
    result = m._stop_incident_broker()
    assert world.commands == ([m._DISABLE, m._BOOTOUT] if expected else [])
    assert world.cleanup == world.handles and len(world.handles) == 1
    assert result["maintenance_state"] == "BROKER_STOPPED_OBSERVED"
    assert result["origin_custody"] is result["provider_called"] is False


@pytest.mark.parametrize("case,code", [
    ("principal", "PRINCIPAL_UNQUALIFIED"), ("consumers", "CONSUMERS_NOT_STOPPED"),
    ("active_broker", "ACTIVE_BROKER"), ("other_owner", "OTHER_ROOT_OWNER"),
    ("drift", "CONTENT_DRIFT"), ("deadline", "DEADLINE_EXCEEDED"),
])
def test_pre_effect_refusals_do_not_issue_any_modifying_verb(world, monkeypatch, case, code):
    if case == "principal": monkeypatch.setattr(m, "os", S(geteuid=lambda: 501))
    if case == "consumers": world.consumer = "RUNNING"
    if case == "active_broker": world.broker = "RUNNING"
    if case == "other_owner": world.other_owner = True
    if case == "drift": world.content_drift_at = 2
    if case == "deadline": monkeypatch.setattr(m, "_BUDGET_NS", 0)
    with pytest.raises(m.BrokerMaintenanceError, match=code) as failure:
        m._stop_incident_broker()
    assert not failure.value.disable_attempted and not failure.value.bootout_attempted
    assert world.commands == [] and world.handles == []


@pytest.mark.parametrize("reply", [(1, b"", b""), (True, b"", b""), (0, b"warning", b""), OSError("lost completion")])
def test_ambiguous_disable_never_proceeds_to_bootout(world, reply):
    world.disable_reply = reply
    with pytest.raises(m.BrokerMaintenanceError) as failure:
        m._stop_incident_broker()
    assert failure.value.disable_attempted and not failure.value.bootout_attempted
    assert world.commands == [m._DISABLE] and world.cleanup == world.handles
    assert len(world.handles) == 1


def test_disabled_readback_failure_never_proceeds_to_bootout(world):
    world.disabled = False
    with pytest.raises(m.BrokerMaintenanceError):
        m._stop_incident_broker()
    assert world.commands == [m._DISABLE]


@pytest.mark.parametrize("reply", [(1, b"", b""), OSError("lost bootout completion")])
def test_failed_bootout_is_never_repeated_or_reported_stopped(world, reply):
    world.bootout_reply = reply
    with pytest.raises(m.BrokerMaintenanceError) as failure:
        m._stop_incident_broker()
    assert failure.value.disable_attempted and failure.value.bootout_attempted
    assert world.commands == [m._DISABLE, m._BOOTOUT] and world.cleanup == world.handles
    assert len(world.handles) == 1


def test_noncanonical_absence_is_not_success(world):
    world.absent_reply = False
    with pytest.raises(m.BrokerMaintenanceError, match="ABSENCE_UNAVAILABLE"):
        m._stop_incident_broker()
    assert world.commands == [m._DISABLE, m._BOOTOUT] and world.cleanup == world.handles
    assert len(world.handles) == 1


@pytest.mark.parametrize("case", ["socket", "old_owner", "source_drift", "post_content_drift", "cleanup"])
def test_post_effect_failures_release_only_owned_handles_and_do_not_repeat(world, monkeypatch, case):
    if case == "socket": monkeypatch.setattr(m.namespace, "_require_socket_absent", Mock(side_effect=ValueError("socket remains")))
    if case == "old_owner": monkeypatch.setattr(m.host, "_observe_old_owner_exclusion", Mock(side_effect=ValueError("owner remains")))
    if case == "source_drift": world.source_drift = True
    if case == "post_content_drift": world.content_drift_at = 4
    if case == "cleanup":
        def fail(handle):
            world.cleanup.append(handle)
            raise OSError("close failure")
        monkeypatch.setattr(m.namespace, "_release_namespace", fail)
    with pytest.raises(m.BrokerMaintenanceError) as failure:
        m._stop_incident_broker()
    assert failure.value.disable_attempted and failure.value.bootout_attempted
    assert world.commands == [m._DISABLE, m._BOOTOUT]
    assert world.cleanup == world.handles and len(world.handles) == 1


def test_cli_arguments_refuse_before_effect(world, monkeypatch):
    call = Mock(side_effect=AssertionError("must not invoke"))
    monkeypatch.setattr(entry, "_stop_incident_broker", call)
    assert entry.main(["--arbitrary-label"]) == 64
    call.assert_not_called()


@pytest.mark.parametrize("attempted,rc", [(False, 65), (True, 75)])
def test_cli_exposes_unknown_effect_boundary(world, monkeypatch, attempted, rc):
    monkeypatch.setattr(entry, "_stop_incident_broker", Mock(side_effect=m.BrokerMaintenanceError(
        "test", disable_attempted=attempted)))
    assert entry.main([]) == rc
