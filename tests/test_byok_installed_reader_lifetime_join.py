"""Protected BYOK constructor joins the actual installed pure READ lifetime.

No role observation: configured asynchronous readers are never invoked. Reuses
retained disposable source/config/namespace/seal/native-child seams, real current
factories, signed fixture principals and canonical phase checks.
"""
import dataclasses
import pytest
from common import fresh_conversation_contract as wire
from control_plane.workspace_read_service import workspace_provider_factory
from control_plane.fresh_conversation_membership import _project_validation_phase, _PHASE, _reader_for_project_phase
from tests.test_fresh_conversation_installed_reader_lifetime import (
    installed_inputs, actual_installed_owner, hosted, room_socket, rsa_key,
)


def configure(a, reader):
    provide = workspace_provider_factory(control_room=a['host'], authorize=a['f']['authorize'],
        armed={}, runtime_identity={}, canonical_project_read_bindings_factory=a['factory'].read_bindings,
        byok_roles_reader=reader)
    binding = dataclasses.replace(a['service']._ceo_ingress_app_binding,
        workspace_read_provider_factory=provide)
    a['service']._ceo_ingress_app_binding = binding
    a['owner']._app = binding
    return provide


def test_configured_async_byok_reader_rejoins_without_metadata_callback(actual_installed_owner):
    a = actual_installed_owner
    calls = []
    async def byok():
        calls.append(True)
        raise AssertionError('pure project READ invoked BYOK observation')
    provide = configure(a, byok)
    f, owner = a['f'], a['owner']
    before = f['before']
    with _project_validation_phase(owner, a['principal'], a['workspace'], f['work']):
        phase = _PHASE.get()
        assert phase.reader._byok_roles_reader is byok
        original_reader, original_binding = phase.reader, phase.binding
        result = owner._project(a['principal'], a['workspace'], f['work'])
        assert wire.canonical_digest(result) == phase.project_digest
        assert phase.reader is original_reader and phase.binding is original_binding
        assert a['service']._ceo_ingress_app_binding.workspace_read_provider_factory is provide
        assert len(a['issued']) == 1
    assert calls == []
    assert before == (len(f['runtime'].events.list_events()), len(f['runtime'].jobs.list_jobs()), len(f['runtime'].attempts.list_attempts()))


def test_rebound_byok_closure_refuses_before_replacement_callback(actual_installed_owner):
    a = actual_installed_owner
    calls = []
    async def original():
        calls.append('original')
    async def replacement():
        calls.append('replacement')
    provide = configure(a, original)
    cell = dict(zip(provide.__code__.co_freevars, provide.__closure__))['byok_roles_reader']
    f, owner = a['f'], a['owner']
    with _project_validation_phase(owner, a['principal'], a['workspace'], f['work']):
        phase = _PHASE.get()
        cell.cell_contents = replacement
        try:
            with pytest.raises(ValueError, match='CONVERSATION_PROJECT_CHANGED'):
                _reader_for_project_phase(owner, a['principal'], a['workspace'], f['work'], provide)
            assert calls == [] and len(a['issued']) == 1
        finally:
            cell.cell_contents = original  # Restore only this disposable fixture's closure before its normal final bracket.
    assert calls == []
    assert f['before'] == (len(f['runtime'].events.list_events()), len(f['runtime'].jobs.list_jobs()), len(f['runtime'].attempts.list_attempts()))
