"""Restart may finish its existing turn, but finite mode never starts a fresh one."""
import pytest
from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor
from control_plane.executive_supervisor import ReconcileStatus
from tests.test_executive_operator_supervisor import _seed_expired_g1, _RecoveryAdapter, _PromptSource


@pytest.mark.parametrize('live,with_turn',[(True,False),(False,True),(True,True)])
def test_foreground_restart_preserves_collection_but_refuses_fresh_resume_or_turn(tmp_path,live,with_turn):
    clock,runtime,root,planner,dispatch,profile,epoch=_seed_expired_g1(
        tmp_path,observed_dead=not live,with_turn=with_turn)
    adapters=[]
    def factory(loader):
        adapter=_RecoveryAdapter(runtime,profile,loader,live_existing=live)
        adapters.append(adapter);return adapter
    supervisor=ExecutiveOperatorSupervisor(runtime,adapter_factory=factory,prompt_source=_PromptSource(),
        foreground_only=True)
    clock.advance(3)
    result=supervisor.reconcile_restart()
    assert len(adapters)==1
    assert adapters[0].resume_calls==adapters[0].begin_turn_calls==0
    expected=ReconcileStatus.OPERATOR_RECOVERED if live and with_turn else ReconcileStatus.LIVE_QUARANTINED
    assert [row.status for row in result]==[expected]
    with runtime.store.read() as c:
        assert c.execute('SELECT count(*) FROM process_generations WHERE session_epoch_id=?',(epoch.session_epoch_id,)).fetchone()[0]==1


def test_foreground_supervisor_without_source_refuses_before_claim(tmp_path):
    import asyncio
    from tests.test_executive_operator_supervisor import _seed_dispatchable_operator_planner
    from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisorError
    runtime,root,planner=_seed_dispatchable_operator_planner(tmp_path)
    supervisor=ExecutiveOperatorSupervisor(runtime,foreground_only=True,
        adapter_factory=lambda _:pytest.fail('unattended adapter'),prompt_source=_PromptSource())
    with pytest.raises(ExecutiveOperatorSupervisorError,match='original request'):
        asyncio.run(supervisor.start_cycle_job(planner.job_id,
            command_id=f'coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1'))
    assert runtime.attempts.list_attempts()==[]
