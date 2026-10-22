"""Actual private factory and canonical admission; physical execution is inert."""
import asyncio
import dataclasses

import pytest

from control_plane import foreground_operation as scope
from tests.test_attended_qualification import selected
from tests.test_foreground_operator_eligibility import real_factory
from tests.test_executive_mcp_installed_fabric_composition import short_socket_root


@pytest.mark.parametrize('edge', ['fresh', 'precommit', 'postcommit', 'replay', 'precommit-remove', 'postcommit-remove'])
def test_actual_factory_qualification_preserves_fresh_and_uncertain_effects(
        tmp_path, short_socket_root, monkeypatch, edge):
    async def run():
        async with real_factory(tmp_path, short_socket_root, monkeypatch) as (service, owner, f, holder):
            service.config = dataclasses.replace(service.config, coo_foreground_only=True,
                coo_attended_work_placements=(selected(f),))
            service._coo_execution_binding = service._load_coo_execution_binding()
            runtime = service._require_runtime()
            drives = []
            async def drive(op, root):
                op.require_root(root)
                assert service._foreground_cycle_owner == (asyncio.current_task(), op)
                service._require_foreground_only_source(root)
                constraints = runtime.jobs.get_job(root).constraints
                assert any(m['provider_realm'] == 'minimax' for m in constraints['work_placement_union'])
                drives.append(root)
                return {'state':'NO_ACTION', 'root_job_id':root, 'delivery':'INCOMPLETE'}
            monkeypatch.setattr(service, '_drive_foreground_cycle', drive)
            def change_qualification():
                q = dataclasses.replace(selected(f).qualification, arguments_sha256='0' * 64)
                service.config = dataclasses.replace(service.config, coo_attended_work_placements=(
                    dataclasses.replace(selected(f), qualification=q),) if not edge.endswith('-remove') else ())
            if edge.startswith('precommit'):
                holder['before_guard'] = change_qualification
            elif edge.startswith('postcommit'):
                original = runtime.jobs.create_v2_orchestration_root
                def commit_then_change(*args, **kwargs):
                    job = original(*args, **kwargs)
                    change_qualification()
                    return job
                monkeypatch.setattr(runtime.jobs, 'create_v2_orchestration_root', commit_then_change)
            async with scope._session_bridge_foreground_dispatch(runtime, f, lambda: None) as op:
                result = await owner.handle_frame(f)
                if edge in {'fresh','replay'}:
                    assert result['ok'] and op._root == result['data']['job_id']
                    assert drives == [op._root]
                else:
                    assert not result['ok'] and op._root is None and drives == []
                    if edge.startswith('postcommit'):
                        assert result['error']['code'] == 'effect_unknown'
            if edge == 'replay':
                async with scope._session_bridge_foreground_dispatch(runtime, f, lambda: None) as op:
                    replay = await owner.handle_frame(f)
                    assert replay['ok'] and replay['data']['duplicate'] and op._root is None
                    assert len(drives) == 1
            assert len(runtime.jobs.list_jobs()) == (0 if edge.startswith('precommit') else 1)
            assert runtime.attempts.list_attempts() == [] and holder['adapters'] == []
            assert service._foreground_cycle_owner is None
    asyncio.run(run())
