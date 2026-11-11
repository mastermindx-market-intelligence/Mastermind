"""Actual service startup/activation separates primary and per-Attempt canaries."""
import asyncio
import tempfile
from pathlib import Path
import pytest
from control_plane.executive_service import ExecutiveControlService
from control_plane.model_router import ModelRouter
from scripts import executive_os_phase1c as cli
from tests.test_fabric_attended_factory_placement import sources, selected, finite_configuration, AttendedControlProbeSource
from tests.test_executive_fabric_composition import root_stats
from tests.test_fabric_attended_routing import router
from tests.test_executive_fabric_phase1c import compose
from tests.test_executive_service import _config


def verdict():
    return dict(schema_version='mastermind.executive_secret_canary/v1',passed=True,
        checks={k:'DENIED' for k in ('control_service_environment','administrative_checkout',
            'executive_database','other_worker_home','forbidden_production_path')},
        receipt_sha256='b'*64,control_environment_probe_sha256='c'*64,
        observed_at='2026-08-11T00:00:00Z',worker_auth_exception='DEDICATED_CODEX_HOME_ONLY')


def test_boot_canary_qualifies_only_primary_owner(tmp_path,monkeypatch,root_stats,router):
    raw,physical,probe=sources(tmp_path,monkeypatch)
    monkeypatch.setattr(ModelRouter,'load',classmethod(lambda cls,*a,**kw:router))
    service,mixed,_=compose(tmp_path,monkeypatch,raw,initial_canary=verdict(),
        fabric_worker_binding_source=physical,fabric_attended_probe_source=probe,
        attended_work_placements=(selected(),))
    assert mixed.primary.secret_canary_verdict==verdict()
    assert mixed.primary.require_complete_launch_attestation is True
    for owner in mixed.owners.values():
        if owner is mixed.primary:continue
        assert owner.secret_canary_verdict=={}
        assert owner.require_complete_launch_attestation is True


def test_quarantined_service_starts_then_activates_only_primary(tmp_path,monkeypatch,root_stats,router):
    raw,physical,probe=sources(tmp_path,monkeypatch)
    monkeypatch.setattr(ModelRouter,'load',classmethod(lambda cls,*a,**kw:router))
    # Capture the production supervisor factory, then exercise the real service
    # with its local inert Runtime/socket. No provider or host calls occur.
    from control_plane import executive_worker_broker as broker
    monkeypatch.setattr(broker,'WorkerBrokerClient',lambda *a,**kw:object())
    monkeypatch.setattr(cli,'activate_launchd_socket',lambda *a:object())
    captured={}
    def capture(config,**kwargs):captured.update(kwargs)
    monkeypatch.setattr(cli,'ExecutiveControlService',capture)
    cli._service_from_config(raw,fabric_worker_binding_source=physical,
        fabric_attended_probe_source=probe,attended_work_placements=(selected(),))
    # Root-installed binding fixture is finished; actual local socket/Runtime
    # must use the real test user's filesystem ownership.
    monkeypatch.undo()
    monkeypatch.setattr(AttendedControlProbeSource, "configuration", finite_configuration(tmp_path))
    async def run():
        with tempfile.TemporaryDirectory(prefix='mm-mixed-') as socket_dir:
            s=ExecutiveControlService(_config(tmp_path,socket_root=Path(socket_dir)),
                supervisor_factory=captured['supervisor_factory'],service_state='AWAITING_CANARY')
            await s.start()
            try:
                assert s.service_state=='AWAITING_CANARY'
                mixed=s.supervisor
                await s.activate_canary(verdict())
                assert s.service_state=='READY'
                assert mixed.primary.secret_canary_verdict==verdict()
                assert mixed.primary.require_complete_launch_attestation is True
                for owner in mixed.owners.values():
                    if owner is mixed.primary:continue
                    assert owner.secret_canary_verdict=={}
                    assert owner.require_complete_launch_attestation is True
                assert s.runtime.attempts.list_attempts()==[]
            finally:await s.close()
    asyncio.run(run())
